#!/bin/bash
# check_perform_mode.sh -- fail-loud health check for the DJ graphics.
# Reads the enforcer heartbeat and reports PASS/CRITICAL. Exit 0 = perform mode
# confirmed active & fresh; exit 1 = NOT active (show graphics degraded).
# Run it any time during the show, or wire it into a monitoring loop.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/log_json.sh"

HB="/tmp/td_perform_state.json"
MAX_AGE=180   # seconds; a heartbeat older than this is stale

if [ ! -f "$HB" ]; then
  echo "CRITICAL: no perform-mode heartbeat ($HB missing) -- enforcer never confirmed"
  log_json critical heartbeat_missing path="$HB"
  exit 1
fi
active=$(/usr/bin/python3 -c "import json;print(json.load(open('$HB')).get('active'))" 2>/dev/null)
ts=$(/usr/bin/python3 -c "import json;print(int(json.load(open('$HB')).get('ts',0)))" 2>/dev/null)
now=$(date +%s)
age=$(( now - ${ts:-0} ))

if [ "$active" != "True" ]; then
  echo "CRITICAL: Perform Mode NOT active -- $(cat "$HB")"
  log_json critical perform_mode_inactive detail="$(cat "$HB" 2>/dev/null)"
  exit 1
fi
if [ "$age" -gt "$MAX_AGE" ]; then
  echo "WARN: Perform Mode heartbeat is stale (${age}s old) -- re-run enforcer to refresh"
  log_json warn heartbeat_stale age_s="$age" max_age_s="$MAX_AGE"
  exit 1
fi
echo "PASS: Perform Mode active (heartbeat ${age}s old)"
log_json info perform_mode_active age_s="$age"
exit 0
