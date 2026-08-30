#!/usr/bin/env python3
"""
Fix "_2" / "_3" duplicate entity_id collisions in the Home Assistant Entity
Registry — without a full wipe-and-restart.

--- Why this happens ---
Every time a YAML template sensor's `unique_id` is bumped (e.g. going from
`tesla_daily_electric_cost_v4` to `_v5`, which happens whenever the sensor's
logic is edited in this project's history) while its `name:` stays the same,
Home Assistant treats it as a brand-new entity:
  - The OLD entity (registered under the old unique_id) is never deleted —
    it just becomes "unavailable" forever, silently squatting the plain
    entity_id (e.g. sensor.tesla_daily_electric_cost).
  - The NEW entity (registered under the new unique_id) can't have that
    slug anymore, so Home Assistant appends "_2" (e.g.
    sensor.tesla_daily_electric_cost_2) — and dashboards/apexcharts-card
    entries still pointing at the plain name show "Entity not available".

A plain Home Assistant restart does NOT fix this: the orphaned old registry
entry persists indefinitely across restarts, since restarting only re-reads
YAML, it doesn't prune the registry. You must explicitly delete the orphan
(or rename the new one) via the Entity Registry API.

--- Why not just run cleanup_legacy_entities.py's full wipe instead? ---
That works, but it's broad: it deletes every entity matching a prefix
across the chosen domains and requires a full HA restart afterward. That
resets `utility_meter` helpers' current-cycle accumulated totals to 0 (e.g.
tesla_daily_charging_energy) and, if input_number is ever included, wipes
lifetime accumulators like input_number.tesla_drive_energy_consumed_total_kwh
back to their YAML `initial:` value. For "just fix the _2 duplicates"
this is more collateral damage than necessary.

This script instead:
  1. Fetches the entity registry AND the live states.
  2. Finds every "sensor.foo_2" (or _3, _4, ...) and groups it with its
     de-suffixed base "sensor.foo" — whether or not that plain entity_id
     still exists. Two situations are handled:
       a) True duplicate pair: "sensor.foo" (orphan, still registered but
          dead) + "sensor.foo_2" (live) both exist. This is the common case
          right after a unique_id bump.
       b) Orphanless leftover: "sensor.foo" was already deleted (by hand,
          or by a previous cleanup pass) but "sensor.foo_2" was never
          renamed back — nothing blocks the plain slug anymore, so it's
          safe to rename directly with no delete step at all. This is what
          you'll see if you already cleaned up the orphan yourself before
          running this script.
  3. Uses live state to figure out which candidate is the real orphan (if
     any): if exactly one candidate has a real value and the rest are
     'unavailable'/'unknown'/missing entirely, the ones without a real
     value are the orphans.
  4. Deletes any orphans, then renames the live entity back to the clean
     "foo" slug — so dashboards referencing the plain entity_id work again
     immediately, no restart needed.
  5. If a group is ambiguous (more than one live candidate, or none at
     all), it is SKIPPED and printed for manual review — this script never
     guesses when it isn't sure. For the orphanless case (1b), a rename is
     only ever proposed when the plain slug is confirmed completely free —
     absent from both the registry and the live states — so it won't touch
     an entity that coincidentally ends in a digit as part of its real name
     (e.g. a second vehicle/charger that was never a "_2" collision).

--- Usage ---
Always dry-run first to review what it found:
  python3 scripts/fix_duplicate_entities.py --url https://your-homeassistant-url --token YOUR_TOKEN --prefix tesla_ --dry-run

Then apply:
  python3 scripts/fix_duplicate_entities.py --url https://your-homeassistant-url --token YOUR_TOKEN --prefix tesla_

Use --prefix "" to scan every entity in Home Assistant instead of just this
project's tesla_/vehicle_ entities (not recommended — could touch unrelated
integrations' duplicates too; only do this if you understand the effect).

Get a Long-Lived Access Token from:
  HA Profile → Long-Lived Access Tokens → Create Token

No third-party dependencies — uses only Python stdlib.
"""

import argparse
import base64
import json
import os
import re
import socket
import ssl
import struct
import sys
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Minimal stdlib WebSocket client (no third-party deps) — same approach as
# cleanup_legacy_entities.py, duplicated here so this script stays a single
# self-contained file you can copy/run independently.
# ---------------------------------------------------------------------------

def _make_frame(payload: bytes) -> bytes:
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    length = len(payload)
    header = bytearray([0x81])  # FIN + text opcode
    if length < 126:
        header.append(0x80 | length)
    elif length < 65536:
        header.append(0x80 | 126)
        header.extend(struct.pack(">H", length))
    else:
        header.append(0x80 | 127)
        header.extend(struct.pack(">Q", length))
    header.extend(mask)
    header.extend(masked)
    return bytes(header)


def _recv_exactly(sock, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("WebSocket connection closed unexpectedly")
        buf += chunk
    return buf


def _recv_frame(sock) -> bytes:
    header = _recv_exactly(sock, 2)
    masked = (header[1] & 0x80) != 0
    length = header[1] & 0x7F
    if length == 126:
        length = struct.unpack(">H", _recv_exactly(sock, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _recv_exactly(sock, 8))[0]
    mask_key = _recv_exactly(sock, 4) if masked else b""
    payload = _recv_exactly(sock, length)
    if masked:
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    return payload


class _WebSocket:
    def __init__(self, url: str, verify_ssl: bool = True):
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        path = parsed.path or "/"

        raw = socket.create_connection((host, port), timeout=15)
        if parsed.scheme == "wss":
            ctx = ssl.create_default_context()
            if not verify_ssl:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            self._sock = ctx.wrap_socket(raw, server_hostname=host)
        else:
            self._sock = raw

        key = base64.b64encode(os.urandom(16)).decode()
        self._sock.sendall((
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}:{port}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"\r\n"
        ).encode())

        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += self._sock.recv(4096)
        status = resp.split(b"\r\n")[0].decode()
        if "101" not in status:
            raise ConnectionError(f"WebSocket upgrade failed: {status}")

    def send(self, text: str):
        self._sock.sendall(_make_frame(text.encode()))

    def recv(self) -> str:
        return _recv_frame(self._sock).decode()

    def close(self):
        try:
            self._sock.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# HA-specific helpers
# ---------------------------------------------------------------------------

def connect_ws(base_url: str, token: str, verify_ssl: bool = True) -> _WebSocket:
    ws_url = base_url.replace("https://", "wss://").replace("http://", "ws://") + "/api/websocket"
    ws = _WebSocket(ws_url, verify_ssl=verify_ssl)

    msg = json.loads(ws.recv())
    if msg.get("type") != "auth_required":
        raise RuntimeError(f"Unexpected initial message: {msg}")

    ws.send(json.dumps({"type": "auth", "access_token": token}))
    msg = json.loads(ws.recv())
    if msg.get("type") != "auth_ok":
        raise RuntimeError(f"Authentication failed: {msg.get('message', msg)}")

    return ws


def ws_call(ws: _WebSocket, msg_id: int, msg_type: str, **kwargs) -> dict:
    ws.send(json.dumps({"id": msg_id, "type": msg_type, **kwargs}))
    return json.loads(ws.recv())


def get_entity_registry(ws: _WebSocket, msg_id: int) -> list[dict]:
    response = ws_call(ws, msg_id, "config/entity_registry/list")
    if not response.get("success"):
        raise RuntimeError(f"Failed to list entity registry: {response}")
    return response["result"]


def get_states(ws: _WebSocket, msg_id: int) -> dict[str, str]:
    response = ws_call(ws, msg_id, "get_states")
    if not response.get("success"):
        raise RuntimeError(f"Failed to get states: {response}")
    return {s["entity_id"]: s["state"] for s in response["result"]}


def delete_entity(ws: _WebSocket, msg_id: int, entity_id: str) -> bool:
    response = ws_call(ws, msg_id, "config/entity_registry/remove", entity_id=entity_id)
    return response.get("success", False)


def rename_entity(ws: _WebSocket, msg_id: int, entity_id: str, new_entity_id: str) -> tuple[bool, dict]:
    response = ws_call(
        ws, msg_id, "config/entity_registry/update",
        entity_id=entity_id, new_entity_id=new_entity_id,
    )
    return response.get("success", False), response


# Matches a trailing numeric suffix HA appends on collision: "_2", "_3", ...
_SUFFIX_RE = re.compile(r"^(?P<base>.+)_(?P<num>\d+)$")


def find_duplicate_groups(entities: list[dict], prefix: str) -> dict[str, list[str]]:
    """Group numerically-suffixed entity_ids (_2, _3, ...) by their
    de-suffixed base — regardless of whether the plain base entity_id still
    exists in the registry. Whether each group is actually actionable (a
    real collision vs. a coincidentally-numbered name) is decided later in
    main() using live state, not here."""
    groups: dict[str, list[str]] = {}

    for e in entities:
        eid = e["entity_id"]
        if prefix and prefix not in eid:
            continue
        domain, _, object_id = eid.partition(".")
        m = _SUFFIX_RE.match(object_id)
        if not m:
            continue
        base_eid = f"{domain}.{m.group('base')}"
        groups.setdefault(base_eid, []).append(eid)

    return groups


def main():
    parser = argparse.ArgumentParser(
        description="Fix _2/_3 duplicate entity_id collisions safely (delete orphan, rename live one back to clean slug)."
    )
    parser.add_argument("--url", required=True, help="HA base URL (no trailing slash)")
    parser.add_argument("--token", required=True, help="Long-Lived Access Token")
    parser.add_argument("--dry-run", action="store_true", help="List planned actions without changing anything")
    parser.add_argument("--no-verify-ssl", action="store_true", help="Skip SSL certificate verification")
    parser.add_argument(
        "--prefix", default="tesla_",
        help="Only consider entity_ids containing this substring (default: 'tesla_'). "
             "Pass --prefix \"\" to scan everything (not recommended).",
    )
    args = parser.parse_args()

    base_url = args.url.rstrip("/")

    print("Connecting to Home Assistant WebSocket API...")
    try:
        ws = connect_ws(base_url, args.token, verify_ssl=not args.no_verify_ssl)
    except Exception as e:
        print(f"❌ Connection/auth failed: {e}")
        sys.exit(1)

    print("Fetching entity registry and live states...")
    try:
        entities = get_entity_registry(ws, 1)
        states = get_states(ws, 2)
    except Exception as e:
        print(f"❌ Failed to fetch data: {e}")
        ws.close()
        sys.exit(1)

    groups = find_duplicate_groups(entities, args.prefix)

    if not groups:
        print(f"✅ No duplicate entity_id groups found matching prefix {args.prefix!r}.")
        ws.close()
        return

    all_ids = {e["entity_id"] for e in entities}
    print(f"\nFound {len(groups)} potential duplicate group(s):\n")

    UNAVAILABLE_STATES = {"unavailable", "unknown", None}
    # Each planned action: (base_eid, orphans_to_delete: list[str], live_eid_to_rename_or_None)
    plan: list[tuple[str, list[str], str | None]] = []
    skipped = []

    for base_eid, dupes in sorted(groups.items()):
        base_in_registry = base_eid in all_ids
        # Only include the plain base as a candidate if it's actually still
        # registered. If it isn't, this is the "orphanless" case — nothing
        # to delete, only a possible rename of the surviving suffixed one.
        candidates = ([base_eid] if base_in_registry else []) + sorted(dupes)
        live = [c for c in candidates if states.get(c) not in UNAVAILABLE_STATES]
        dead = [c for c in candidates if states.get(c) in UNAVAILABLE_STATES]

        label = ", ".join(candidates)
        if not base_in_registry:
            label += f"  (base {base_eid!r} not in registry — orphanless case)"
        print(f"  Group: {label}")
        for c in candidates:
            print(f"    - {c:<55} state={states.get(c, '(no state)')}")

        if not (len(live) == 1 and len(dead) == len(candidates) - 1):
            skipped.append(candidates)
            print(f"    -> SKIPPED (ambiguous: {len(live)} live, {len(dead)} dead) — review manually")
            print()
            continue

        live_eid = live[0]

        if not base_in_registry and states.get(base_eid) not in UNAVAILABLE_STATES:
            # Extra safety net: the plain slug isn't in the registry but
            # something is nonetheless reporting a live state under that
            # exact entity_id (very unusual) — don't touch it.
            skipped.append(candidates)
            print(f"    -> SKIPPED ({base_eid!r} has an unexpected live state outside the registry — review manually)")
            print()
            continue

        rename_needed = live_eid != base_eid
        plan.append((base_eid, dead, live_eid if rename_needed else None))

        if dead and rename_needed:
            print(f"    -> PLAN: delete {dead}, then rename {live_eid!r} -> {base_eid!r}")
        elif dead:
            print(f"    -> PLAN: delete {dead} (already correctly named {base_eid!r})")
        elif rename_needed:
            print(f"    -> PLAN: rename {live_eid!r} -> {base_eid!r} (no delete needed — base already free)")
        print()

    if not plan:
        print("Nothing safe to auto-fix. See skipped groups above for manual review.")
        ws.close()
        return

    if args.dry_run:
        print("Dry run — nothing changed. Remove --dry-run to execute.")
        ws.close()
        return

    print("Applying fixes...\n")
    msg_id = 3
    fixed = 0
    failed = 0
    for base_eid, orphans, rename_from in plan:
        for orphan_eid in orphans:
            ok = delete_entity(ws, msg_id, orphan_eid)
            msg_id += 1
            if ok:
                print(f"  ✅ Deleted orphan: {orphan_eid}")
                fixed += 1
            else:
                print(f"  ⚠️  Could not delete: {orphan_eid}")
                failed += 1

        if rename_from:
            ok, resp = rename_entity(ws, msg_id, rename_from, base_eid)
            msg_id += 1
            if ok:
                print(f"  ✅ Renamed {rename_from} -> {base_eid}")
                fixed += 1
            else:
                print(f"  ⚠️  Could not rename {rename_from} -> {base_eid}: {resp}")
                failed += 1

    ws.close()
    print(f"\nDone: {fixed} action(s) succeeded, {failed} failed.")
    if skipped:
        print(f"{len(skipped)} group(s) skipped as ambiguous — check them manually in Settings → Entities.")
    print("No Home Assistant restart is required — changes take effect immediately.")


if __name__ == "__main__":
    main()
