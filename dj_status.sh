#!/bin/bash
# dj_status.sh -- green-check status of the whole DJ graphics stack.
# Writes /tmp/dj_status.log and prints PASS/FAIL per component. Run after the
# launcher's ACTIVATE (or wire into the launcher's post-start step).
LOG=/tmp/dj_status.log
: > "$LOG"
ok(){ echo "  ✅ $1" | tee -a "$LOG"; }
bad(){ echo "  ❌ $1" | tee -a "$LOG"; }
echo "==== DJ STATUS $(date) ====" | tee -a "$LOG"

pgrep -f 'MacOS/TouchDesigner' >/dev/null && ok "TouchDesigner running" || bad "TouchDesigner NOT running"

if [ -f /tmp/td_perform_state.json ] && grep -q '"on_hisense": true' /tmp/td_perform_state.json 2>/dev/null; then
  ok "Perform Mode active on HISENSE"
else bad "Perform Mode NOT confirmed on HISENSE (run perform_enforcer.sh)"; fi

pgrep -f 'movement_tracker.py' >/dev/null && ok "Body tracker running" || bad "Body tracker NOT running"

# seqlock writer alive = .seq advancing
if [ -f /tmp/djsam_bodymask.seq ]; then
  s1=$(/usr/bin/python3 -c "import struct;print(struct.unpack('<Q',open('/tmp/djsam_bodymask.seq','rb').read(8))[0])" 2>/dev/null||echo 0)
  sleep 1
  s2=$(/usr/bin/python3 -c "import struct;print(struct.unpack('<Q',open('/tmp/djsam_bodymask.seq','rb').read(8))[0])" 2>/dev/null||echo 0)
  if [ "$s2" -gt "$s1" ] 2>/dev/null; then ok "Seqlock mask streaming (seq $s1->$s2, ~$((s2-s1)) fps)"; else bad "Seqlock seq NOT advancing (tracker/camera issue)"; fi
else bad "Seqlock .seq file missing"; fi

pgrep -f 'MacOS/Serato' >/dev/null && ok "Serato running" || bad "Serato NOT running"
pgrep -f 'MacOS/OBS'    >/dev/null && ok "OBS running" || bad "OBS NOT running"

# announcer on 17900
curl -s --max-time 3 http://127.0.0.1:17900/health >/dev/null 2>&1 && ok "Serato announcer serving :17900" || bad "Announcer NOT serving :17900"

echo "---- log: $LOG ----"
