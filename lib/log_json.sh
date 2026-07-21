#!/bin/bash
# lib/log_json.sh -- shared NDJSON logger for the DJ suite shell scripts (SH-2).
#
# Before this: five scripts, five log formats (bare echo, exec-redirected
# prose, tee'd raw Python output), none machine-readable. Only the enforcer's
# heartbeat file was structured JSON, and it's a single overwritten value with
# no history. This gives every script the same append-only NDJSON stream so
# the watchdog agent can consume `event`/`level` without regexing prose.
#
# Usage: source this file, then call:
#   log_json <level> <event> [key=value ...]
# level is info|warn|critical. Writes one line to
# logs/<calling-script-basename>.ndjson. Does not replace the script's normal
# echo/stdout -- this is an additional structured stream, not a UI.
set -u

LOG_JSON_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/logs"
mkdir -p "$LOG_JSON_DIR"
LOG_JSON_SCRIPT="$(basename "${BASH_SOURCE[1]:-$0}")"
LOG_JSON_FILE="$LOG_JSON_DIR/${LOG_JSON_SCRIPT%.*}.ndjson"

log_json() {
  local level="$1" event="$2"
  shift 2 || shift $#
  local detail_json="{" first=1 kv k v
  for kv in "$@"; do
    k="${kv%%=*}"
    v="${kv#*=}"
    [ "$first" -eq 1 ] || detail_json+=","
    first=0
    if [[ "$v" =~ ^-?[0-9]+(\.[0-9]+)?$ ]] || [[ "$v" == "true" || "$v" == "false" ]]; then
      detail_json+="\"$k\":$v"
    else
      v="${v//\\/\\\\}"
      v="${v//\"/\\\"}"
      detail_json+="\"$k\":\"$v\""
    fi
  done
  detail_json+="}"
  printf '{"ts":%s,"script":"%s","level":"%s","event":"%s","detail":%s}\n' \
    "$(date +%s)" "$LOG_JSON_SCRIPT" "$level" "$event" "$detail_json" >> "$LOG_JSON_FILE"
}
