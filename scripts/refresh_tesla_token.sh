#!/usr/bin/env bash
#
# refresh_tesla_token.sh
#
# Extracts the current Tesla Fleet OAuth access_token from Home Assistant's
# own config-entry storage and writes it into secrets.yaml, so the
# `rest_command.tesla_window_close_gps` workaround (used by the
# `tesla_windows_close` script — see packages/tesla/scripts.yaml) keeps
# working without you having to manually open/search a huge minified JSON
# file and copy-paste a token by hand.
#
# WHY THIS EXISTS:
# Home Assistant's Tesla Fleet integration auto-refreshes its own OAuth
# token internally, but that refreshed token is never exposed through the
# frontend/REST/WebSocket API (by design, for security) — so scripts that
# call the raw Tesla Fleet Cloud API directly (like the window-close GPS
# workaround in this project) can't fetch it remotely. The only place it
# lives is inside Home Assistant's own on-disk config-entry storage file,
# `.storage/core.config_entries`, under the `tesla_fleet` integration's
# entry, as data.token.access_token. That token expires roughly every
# ~8 hours, so this script needs to be re-run periodically.
#
# WHERE TO RUN THIS:
# This must run *on the Home Assistant host itself* (or wherever /config is
# mounted) — e.g. via the "Terminal & SSH" add-on's shell, NOT from your
# separate dev machine, since `.storage/core.config_entries` is not
# reachable over the network/API. Copy this script onto the HA host first
# (via the Samba/File Editor add-on, or `scp`), then run it there.
#
# USAGE (run inside the HA host's SSH/Terminal shell):
#   bash refresh_tesla_token.sh                # dry run: prints masked token, changes nothing
#   bash refresh_tesla_token.sh --apply         # writes the token into /config/secrets.yaml
#   bash refresh_tesla_token.sh --apply --restart   # also restarts Home Assistant afterwards
#   bash refresh_tesla_token.sh --config-path /config --apply   # custom /config path
#
# SAFETY:
# - Dry-run by default; nothing is written unless --apply is passed.
# - Always backs up secrets.yaml to secrets.yaml.bak-<timestamp> before editing.
# - Never prints the full token to the terminal unless --show is passed
#   (only a masked preview is shown otherwise), to avoid it lingering in
#   your shell's scrollback/history.
# - Never commit secrets.yaml or any file containing a real token to git —
#   secrets.yaml is already gitignored in this project; keep it that way.
#
# TROUBLESHOOTING — "command not found" / "invalid option name: pipefail":
# This means the file picked up Windows-style CRLF line endings during the
# copy to your HA host (common if you opened/saved it with a Windows editor,
# or dragged it over a Samba share that re-saved it). Bash cannot reliably
# self-repair this from inside the same corrupted script (its own if/case
# keywords break the same way), so fix it manually first, then re-run:
#   sed -i 's/\r$//' refresh_tesla_token.sh
#   bash refresh_tesla_token.sh --apply --restart
# To avoid this happening again, prefer `scp`/`curl` (raw byte copy) over
# opening the file in a Windows text editor before transferring it.

set -euo pipefail

CONFIG_PATH="/config"
APPLY=0
RESTART=0
SHOW=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config-path) CONFIG_PATH="$2"; shift 2 ;;
    --apply) APPLY=1; shift ;;
    --restart) RESTART=1; shift ;;
    --show) SHOW=1; shift ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^#//'
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

ENTRIES_FILE="$CONFIG_PATH/.storage/core.config_entries"
SECRETS_FILE="$CONFIG_PATH/secrets.yaml"

if [[ ! -f "$ENTRIES_FILE" ]]; then
  echo "ERROR: $ENTRIES_FILE not found. Pass --config-path if your /config lives elsewhere." >&2
  exit 1
fi

TOKEN=""

# Preferred: python3 (robust JSON parsing, handles nested structure safely).
if command -v python3 >/dev/null 2>&1; then
  TOKEN="$(python3 - "$ENTRIES_FILE" <<'PYEOF'
import json, sys
with open(sys.argv[1]) as f:
    data = json.load(f)
for entry in data.get("data", {}).get("entries", []):
    if entry.get("domain") == "tesla_fleet":
        token = entry.get("data", {}).get("token", {}).get("access_token")
        if token:
            print(token)
            break
PYEOF
)"
# Fallback: jq (also handles nested JSON safely).
elif command -v jq >/dev/null 2>&1; then
  TOKEN="$(jq -r '.data.entries[] | select(.domain=="tesla_fleet") | .data.token.access_token // empty' "$ENTRIES_FILE" | head -n1)"
else
  echo "ERROR: neither python3 nor jq is available in this shell." >&2
  echo "Install one (e.g. 'apk add python3' or 'apk add jq' on the HAOS SSH/Terminal add-on) and re-run." >&2
  exit 1
fi

if [[ -z "$TOKEN" ]]; then
  echo "ERROR: could not find a tesla_fleet access_token in $ENTRIES_FILE." >&2
  echo "Make sure the Tesla Fleet integration is set up and has connected at least once." >&2
  exit 1
fi

MASKED="${TOKEN:0:8}...${TOKEN: -6}"

if [[ "$SHOW" -eq 1 ]]; then
  echo "Token found: $TOKEN"
else
  echo "Token found: $MASKED (pass --show to print in full)"
fi

if [[ "$APPLY" -eq 0 ]]; then
  echo
  echo "Dry run — nothing written. Re-run with --apply to update $SECRETS_FILE."
  exit 0
fi

if [[ ! -f "$SECRETS_FILE" ]]; then
  echo "ERROR: $SECRETS_FILE not found. Create it from secrets.yaml.example first." >&2
  exit 1
fi

# Idempotency check: skip the write entirely (no backup, no "Updated" message)
# if the token in secrets.yaml already matches what we just fetched. This
# matters for scheduled/unattended runs (see the tesla_refresh_fleet_token
# automation in packages/tesla/automations.yaml) — that automation greps
# this script's stdout for the literal string "Updated tesla_fleet_token" to
# decide whether to notify you that a restart would help; without this
# check it would fire that notification every single run, even when nothing
# actually changed.
CURRENT_TOKEN="$(grep '^tesla_fleet_token:' "$SECRETS_FILE" 2>/dev/null | sed -E 's/^tesla_fleet_token:[[:space:]]*"?([^"]*)"?[[:space:]]*$/\1/')"
if [[ "$CURRENT_TOKEN" == "$TOKEN" ]]; then
  echo "Token unchanged — secrets.yaml already up to date. Nothing written."
  exit 0
fi

BACKUP="$SECRETS_FILE.bak-$(date +%Y%m%d%H%M%S)"
cp "$SECRETS_FILE" "$BACKUP"
echo "Backed up secrets.yaml to $BACKUP"

if grep -q '^tesla_fleet_token:' "$SECRETS_FILE"; then
  # Replace existing line.
  sed -i "s|^tesla_fleet_token:.*|tesla_fleet_token: \"$TOKEN\"|" "$SECRETS_FILE"
else
  # Append a new line.
  printf '\ntesla_fleet_token: "%s"\n' "$TOKEN" >> "$SECRETS_FILE"
fi
echo "Updated tesla_fleet_token in $SECRETS_FILE."

if [[ "$RESTART" -eq 1 ]]; then
  if command -v ha >/dev/null 2>&1; then
    echo "Restarting Home Assistant Core via 'ha core restart'..."
    ha core restart
  else
    echo "WARNING: 'ha' CLI not found in this shell — restart Home Assistant manually" >&2
    echo "(Settings → System → Restart) for the new token to take effect." >&2
  fi
else
  echo "Restart Home Assistant (Settings → System → Restart) for the new token to take effect."
fi
