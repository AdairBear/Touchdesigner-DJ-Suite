#!/bin/bash
# perform_enforcer.sh -- BULLETPROOF external Perform Mode trigger + fail-loud.
# ---------------------------------------------------------------------------
# TD's internal auto-perform (project.performOnStart / Execute DAT) is racy on
# this build -- it engages some launches and not others. This external enforcer
# does NOT depend on TD internals: it waits for TD to be up, then repeatedly
# drives `ui.performMode = True` via the Textport (osascript) and VERIFIES it
# took, retrying until confirmed. If it can't confirm within the budget it
# writes a CRITICAL heartbeat and exits non-zero so the launcher/health check
# screams. The DJ show is broken without Perform Mode -- this is exits-are-sacred.
#
# Launched in the background by start_tracker.command (which the TD DJ Launcher
# runs first). Also runnable by hand:  bash perform_enforcer.sh
#
# Dev opt-out: `touch /tmp/td_no_autoperform` before launching -> enforcer skips.
# ---------------------------------------------------------------------------
set -u
REPO="/Users/thomasadair/projects/touchdesigner-dj-suite"
TD_SCRIPT="$REPO/touchdesigner/scripts/_enforce_perform.py"
HB="/tmp/td_perform_state.json"
SKIP="/tmp/td_no_autoperform"
LOG="/tmp/perform_enforcer.log"
MAX_WAIT_TD=90       # s to wait for TD process
LOAD_GRACE=10        # s to let the project deserialize after TD appears
MAX_ATTEMPTS=25      # perform-enter attempts (~ MAX_ATTEMPTS*3s)

exec >>"$LOG" 2>&1
echo "==== perform_enforcer start $(date) ===="

if [ -f "$SKIP" ]; then
  echo "opt-out ($SKIP) present -> not enforcing perform mode (dev session)"
  exit 0
fi

# 1. Wait for TouchDesigner to be running.
for i in $(seq 1 "$MAX_WAIT_TD"); do
  if pgrep -f 'MacOS/TouchDesigner' >/dev/null 2>&1; then echo "TD up after ${i}s"; break; fi
  sleep 1
done
if ! pgrep -f 'MacOS/TouchDesigner' >/dev/null 2>&1; then
  echo "CRITICAL: TouchDesigner never started within ${MAX_WAIT_TD}s"
  printf '{"active": false, "reason": "CRITICAL TD-not-running", "ts": %s}\n' "$(date +%s)" > "$HB"
  exit 1
fi
sleep "$LOAD_GRACE"

send_enforce() {
  osascript >/dev/null 2>&1 <<AS
tell application "TouchDesigner" to activate
delay 0.4
tell application "System Events"
  tell process "TouchDesigner"
    try
      click menu item "Textport and DATs" of menu "Dialogs" of menu bar 1
    end try
    delay 0.5
    keystroke "exec(open('${TD_SCRIPT}').read())"
    delay 0.2
    key code 36
  end tell
end tell
AS
}

# 2. Drive perform mode until confirmed active.
for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  [ -f "$SKIP" ] && { echo "opt-out appeared mid-run -> stop"; exit 0; }
  rm -f "$HB"
  send_enforce
  for w in 1 2 3 4 5; do [ -f "$HB" ] && break; sleep 1; done
  # A fatal window error (e.g. "Invalid window size") throws a BLOCKING modal.
  # Do NOT keep retrying -- that just spams the modal Thomas can't dismiss.
  # Page once and stop; the window params need fixing (setup_perform_mode.py).
  if [ -f "$HB" ] && grep -q '"fatal": true' "$HB"; then
    echo "CRITICAL: /project1/perform has a fatal window error -- STOPPING to avoid modal spam. $(cat "$HB")"
    exit 1
  fi
  # Success requires BOTH active AND on the HISENSE display -- an active perform
  # window on the wrong monitor (Samsung) is exactly the failure we're fixing.
  if [ -f "$HB" ] && grep -q '"active": true' "$HB" && grep -q '"on_hisense": true' "$HB"; then
    echo "PERFORM MODE ACTIVE ON HISENSE (attempt $attempt) $(cat "$HB")"
    exit 0
  fi
  echo "attempt $attempt: not on HISENSE yet ($(cat "$HB" 2>/dev/null))"
  sleep 2
done

echo "CRITICAL: Perform Mode NOT active after $MAX_ATTEMPTS attempts -- SHOW GRAPHICS DEGRADED"
printf '{"active": false, "reason": "CRITICAL enforcer-exhausted", "ts": %s}\n' "$(date +%s)" > "$HB"
exit 1
