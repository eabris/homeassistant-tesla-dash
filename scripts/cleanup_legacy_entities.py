#!/usr/bin/env python3
"""
Delete orphaned legacy entities from Home Assistant after a vehicle rename
or alias-prefix migration (e.g. after running rename_tesla_prefix.py, or
renaming a vehicle from "daddy_taxi" to "tesla" in your YAML).

Before running, set LEGACY_PREFIX below to the old vehicle entity prefix
(e.g. "my_model_x", "model_y", "cybertruck", "daddy_taxi").

By default this only touches sensor/binary_sensor entities (safe default,
matches historical behavior). Pass --all-domains to also clean up orphaned
script, automation, and input_* helper entities left behind in the Entity
Registry after you've renamed those in YAML and reloaded HA — those old
entries don't get removed automatically just because YAML no longer
defines them.

Note: renaming (instead of deleting) is NOT offered as an option here.
Once YAML has been updated to the new prefix, HA already created fresh
entities with new unique_ids for the new names; the orphaned old entities
cannot be "reconnected" to them, and per-entity_id-keyed history/statistics
don't carry over on rename anyway (see agents.md Technical Appendix,
section 4). Deleting the orphans is the only thing that actually helps.

Usage:
  python3 scripts/cleanup_legacy_entities.py --url https://your-homeassistant-url --token YOUR_TOKEN [--all-domains] [--dry-run]

Get a Long-Lived Access Token from:
  HA Profile → Long-Lived Access Tokens → Create Token

No third-party dependencies — uses only Python stdlib.
"""

import argparse
import base64
import hashlib
import json
import os
import socket
import ssl
import struct
import sys
from urllib.parse import urlparse

# ---- CONFIGURE THIS ----
# Set this to the old vehicle entity prefix you want to clean up.
# Example: "my_model_x", "model_y", "cybertruck"
LEGACY_PREFIX = "cybertruck"
# -------------------------

# Domains to scan for removal by default (safe: no user-configured helpers)
DELETE_DOMAINS = {"sensor", "binary_sensor"}

# Extra domains included when --all-domains is passed. These are the ones
# that show up as orphaned scripts/automations/input_* rows after a rename.
ALL_DOMAINS_EXTRA = {
    "script", "automation",
    "input_number", "input_boolean", "input_text", "input_datetime", "input_select",
}

# Specific entity IDs to KEEP even if they match LEGACY_PREFIX in the above domains
# (Add any you want to preserve)
KEEP_ENTITIES = set()


# ---------------------------------------------------------------------------
# Minimal stdlib WebSocket client (no third-party deps)
# ---------------------------------------------------------------------------

def _make_frame(payload: bytes) -> bytes:
    """Build a masked client→server WebSocket text frame."""
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
    """Read one WebSocket frame and return its unmasked payload."""
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


def get_entity_registry(ws: _WebSocket) -> list[dict]:
    response = ws_call(ws, 1, "config/entity_registry/list")
    if not response.get("success"):
        raise RuntimeError(f"Failed to list entity registry: {response}")
    return response["result"]


def delete_entity(ws: _WebSocket, msg_id: int, entity_id: str) -> bool:
    response = ws_call(ws, msg_id, "config/entity_registry/remove", entity_id=entity_id)
    return response.get("success", False)


def main():
    parser = argparse.ArgumentParser(description=f"Clean up orphaned {LEGACY_PREFIX} entities")
    parser.add_argument("--url", required=True, help="HA base URL (no trailing slash)")
    parser.add_argument("--token", required=True, help="Long-Lived Access Token")
    parser.add_argument("--dry-run", action="store_true", help="List without deleting")
    parser.add_argument("--no-verify-ssl", action="store_true", help="Skip SSL certificate verification")
    parser.add_argument(
        "--all-domains", action="store_true",
        help="Also clean up orphaned script/automation/input_* entities "
             "(not just sensor/binary_sensor). Use this after renaming a "
             "vehicle prefix in YAML and reloading HA.",
    )
    args = parser.parse_args()

    base_url = args.url.rstrip("/")
    domains = DELETE_DOMAINS | ALL_DOMAINS_EXTRA if args.all_domains else DELETE_DOMAINS

    print("Connecting to Home Assistant WebSocket API...")
    try:
        ws = connect_ws(base_url, args.token, verify_ssl=not args.no_verify_ssl)
    except Exception as e:
        print(f"❌ Connection/auth failed: {e}")
        sys.exit(1)

    print("Fetching entity registry...")
    try:
        entities = get_entity_registry(ws)
    except Exception as e:
        print(f"❌ Failed to fetch entities: {e}")
        ws.close()
        sys.exit(1)

    candidates = [
        e for e in entities
        if LEGACY_PREFIX in e["entity_id"]
        and e["entity_id"].split(".")[0] in domains
        and e["entity_id"] not in KEEP_ENTITIES
    ]

    if not candidates:
        print(f"✅ No orphaned {LEGACY_PREFIX} sensor/binary_sensor entities found.")
        ws.close()
        return

    print(f"\nFound {len(candidates)} entities to {'delete' if not args.dry_run else 'delete (DRY RUN)'}:\n")
    for e in candidates:
        status = e.get("disabled_by") or "active"
        print(f"  {'[DRY]' if args.dry_run else '    '} {e['entity_id']:<60} ({status})")

    if args.dry_run:
        print("\nDry run — nothing deleted. Remove --dry-run to execute.")
        ws.close()
        return

    print()
    deleted = 0
    failed = 0
    for i, e in enumerate(candidates, start=2):  # msg_id 1 was used for list
        eid = e["entity_id"]
        if delete_entity(ws, i, eid):
            print(f"  ✅ Deleted: {eid}")
            deleted += 1
        else:
            print(f"  ⚠️  Could not delete (still active?): {eid}")
            failed += 1

    ws.close()
    print(f"\nDone: {deleted} deleted, {failed} skipped (still active in config — reload HA first).")
    if failed:
        print("Tip: Reload HA config first, then run this script again for the skipped ones.")


if __name__ == "__main__":
    main()
