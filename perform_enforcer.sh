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
PIDFILE="/tmp/perform_enforcer.pid"

# shellcheck source=lib/log_json.sh
source "$REPO/lib/log_json.sh"

exec >>"$LOG" 2>&1
echo "==== perform_enforcer start $(date) ===="
log_json info enforcer_start

# SH-4: single-instance guard. Re-running start_tracker.command (the
# documented recovery for a tracker crash) used to spawn a second enforcer
# while the first was still mid-loop -- both rm'd the same heartbeat and both
# typed into the Textport, fighting each other for 3.5 minutes.
if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; then
  echo "already running as pid $(cat "$PIDFILE") -- exiting"
  log_json info enforcer_already_running existing_pid="$(cat "$PIDFILE")"
  exit 0
fi
echo $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT

if [ -f "$SKIP" ]; then
  echo "opt-out ($SKIP) present -> not enforcing perform mode (dev session)"
  log_json info enforcer_skip reason=dev_opt_out
  exit 0
fi

# 1. Wait for TouchDesigner to be running.
for i in $(seq 1 "$MAX_WAIT_TD"); do
  if pgrep -f 'MacOS/TouchDesigner' >/dev/null 2>&1; then echo "TD up after ${i}s"; break; fi
  sleep 1
done
if ! pgrep -f 'MacOS/TouchDesigner' >/dev/null 2>&1; then
  echo "CRITICAL: TouchDesigner never started within ${MAX_WAIT_TD}s"
  printf '{"active": false, "reason": "CRITICAL TD-not-running", "ts": %s}\n' "$(date +%s)" > "$HB.tmp" && mv -f "$HB.tmp" "$HB"
  log_json critical td_never_started max_wait_s="$MAX_WAIT_TD"
  exit 1
fi
sleep "$LOAD_GRACE"

# ---------------------------------------------------------------------------
# 2026-08-01 -- PHANTOM "newproject.toe" FIX. This gate is the whole reason
# ACTIVATE was coming up with a blank default project instead of the canonical
# .toe.
#
# The race, exactly:
#
#   ACTIVATE stage 1 opens start_tracker.command, which backgrounds THIS script
#   (start_tracker.command:41). ACTIVATE stage 2 then opens the .toe.
#
#   This script waited for the TouchDesigner PROCESS (`pgrep`, line ~54) and
#   then slept LOAD_GRACE=10s. But a TD process exists within a second or two of
#   `open`, while a measured COLD LOAD of this project takes 142-203s. So the
#   grace expired roughly 130-190 SECONDS before the project window existed, and
#   send_enforce() ran `tell application "TouchDesigner" to activate` against a
#   TD still sitting on its splash screen.
#
#   An `activate` sent to TouchDesigner with no front window is interpreted as
#   "open a new empty document". That is the phantom blank project. The launcher
#   knows this and guards its OWN activate behind a window-confirmation gate
#   (agent/sequencer.py's _stage_td, and AppLauncher.confirmTDProjectLoaded) --
#   but this script is launched as a side effect of stage 1 and raced ahead of
#   both of them.
#
# The fix is to gate on the PROJECT, not the process: poll until TD reports a
# window whose title carries a .toe path. System Events READS the window list;
# it does not activate anything, so the probe itself cannot trigger the bug.
#
# Phantom titles are excluded explicitly. If a phantom is already open we must
# not treat it as success -- that would enforce Perform Mode on the blank
# project and report green.
MAX_WAIT_PROJECT=240   # matches sequencer.TD_TIMEOUT_S; measured loads are 142-203s
PROJECT_POLL=3

td_project_window() {
  osascript -e 'tell application "System Events" to tell process "TouchDesigner" to get name of every window' 2>/dev/null
}

echo "waiting up to ${MAX_WAIT_PROJECT}s for TD's PROJECT window (not just the process)"
project_confirmed=0
for _ in $(seq 1 $((MAX_WAIT_PROJECT / PROJECT_POLL))); do
  titles=$(td_project_window)
  case "$(printf '%s' "$titles" | tr '[:upper:]' '[:lower:]')" in
    *newproject*|*untitled*)
      echo "CRITICAL: TD already has a phantom/blank project open: $titles"
      log_json critical td_phantom_project titles="$titles"
      printf '{"active": false, "reason": "CRITICAL phantom-blank-project", "ts": %s}\n' \
        "$(date +%s)" > "$HB.tmp" && mv -f "$HB.tmp" "$HB"
      rm -f "$PIDFILE"
      exit 1
      ;;
    *.toe*)
      echo "project window confirmed: $titles"
      log_json info td_project_window_confirmed titles="$titles"
      project_confirmed=1
      break
      ;;
  esac
  sleep "$PROJECT_POLL"
done

if [ "$project_confirmed" -ne 1 ]; then
  echo "CRITICAL: no TD project window within ${MAX_WAIT_PROJECT}s -- NOT sending activate"
  echo "CRITICAL: (an activate now would make TD open a phantom blank project)"
  log_json critical td_project_window_timeout max_wait_s="$MAX_WAIT_PROJECT"
  printf '{"active": false, "reason": "CRITICAL project-window-never-appeared", "ts": %s}\n' \
    "$(date +%s)" > "$HB.tmp" && mv -f "$HB.tmp" "$HB"
  exit 1
fi
# ---------------------------------------------------------------------------

# 2026-07-31 -- BLIND TYPING GUARD.
#
# This function types a long literal string and presses Return. It assumed
# `activate` + `delay 0.4` had put TouchDesigner in front. That assumption is
# not safe: activation is asynchronous, TD's splash "silently swallows
# keystrokes" (this repo's own words), and during ACTIVATE the launcher opens
# OBS, Serato and BUTT right after TD -- each stealing focus. The 2026-07-28
# handoff records this path failing repeatedly with `_enforce_perform.py` never
# executing, which means those keystrokes went SOMEWHERE ELSE.
#
# What gets typed is:
#   exec(open('.../touchdesigner-dj-suite/touchdesigner/scripts/_enforce_perform.py').read())
#
# That string contains HYPHENS ("touchdesigner-dj-suite"). In Serato DJ, `-` is
# the waveform zoom shortcut. A few of these landing in a frontmost Serato is a
# straight-line explanation for a waveform zoomed to its extreme -- and for the
# launcher appearing to have "changed a Serato preference" without any Apple
# Event that does so existing anywhere in either repo.
#
# So: confirm TouchDesigner is ACTUALLY frontmost immediately before typing, and
# abort if it is not. Not typing costs one enforcer attempt, which retries.
# Typing into the wrong app costs the operator's Serato setup mid-show.
send_enforce() {
  osascript >/dev/null 2>&1 <<AS
tell application "TouchDesigner" to activate
delay 0.8
tell application "System Events"
  set frontApp to name of first application process whose frontmost is true
  if frontApp is not "TouchDesigner" then
    do shell script "echo 'perform_enforcer: REFUSED to type -- frontmost was ' & quoted form of frontApp & ', not TouchDesigner' >&2"
    return
  end if
  tell process "TouchDesigner"
    try
      click menu item "Textport and DATs" of menu "Dialogs" of menu bar 1
    end try
    delay 0.5
    -- Re-check after the menu click: opening the Textport can move focus.
    set frontApp2 to name of first application process whose frontmost is true
    if frontApp2 is not "TouchDesigner" then return
    keystroke "exec(open('${TD_SCRIPT}').read())"
    delay 0.2
    key code 36
  end tell
end tell
AS
}

# Read the heartbeat's own "ts" field (0 if missing/unparseable). Used instead
# of `rm -f "$HB"` + file-existence: the Python side now writes atomically
# (OBS-4), so the file is never observed mid-write, and here we wait for ts to
# *advance* past the pre-attempt value rather than deleting the file between
# attempts -- deleting created a window where a reader (e.g. check_perform_mode.sh
# running concurrently) could see "no heartbeat" and report a false CRITICAL.
read_hb_ts() {
  [ -f "$HB" ] || { echo 0; return; }
  /usr/bin/python3 -c "import json;print(json.load(open('$HB')).get('ts',0))" 2>/dev/null || echo 0
}

# 2. Drive perform mode until confirmed active.
for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  [ -f "$SKIP" ] && { echo "opt-out appeared mid-run -> stop"; exit 0; }
  prev_ts=$(read_hb_ts)
  send_enforce
  fresh=""
  for w in 1 2 3 4 5; do
    cur_ts=$(read_hb_ts)
    if awk -v a="$cur_ts" -v b="$prev_ts" 'BEGIN{exit !(a>b)}'; then fresh=1; break; fi
    sleep 1
  done
  # A fatal window error (e.g. "Invalid window size") throws a BLOCKING modal.
  # Do NOT keep retrying -- that just spams the modal Thomas can't dismiss.
  # Page once and stop; the window params need fixing (setup_perform_mode.py).
  if [ -n "$fresh" ] && grep -q '"fatal": true' "$HB"; then
    echo "CRITICAL: /project1/perform has a fatal window error -- STOPPING to avoid modal spam. $(cat "$HB")"
    log_json critical fatal_window_error attempt="$attempt"
    exit 1
  fi
  # Success requires BOTH active AND on the HISENSE display -- an active perform
  # window on the wrong monitor (Samsung) is exactly the failure we're fixing.
  if [ -n "$fresh" ] && grep -q '"active": true' "$HB" && grep -q '"on_hisense": true' "$HB"; then
    echo "PERFORM MODE ACTIVE ON HISENSE (attempt $attempt) $(cat "$HB")"
    log_json info perform_mode_active attempt="$attempt"
    exit 0
  fi
  echo "attempt $attempt: not on HISENSE yet ($(cat "$HB" 2>/dev/null))"
  sleep 2
done

echo "CRITICAL: Perform Mode NOT active after $MAX_ATTEMPTS attempts -- SHOW GRAPHICS DEGRADED"
printf '{"active": false, "reason": "CRITICAL enforcer-exhausted", "ts": %s}\n' "$(date +%s)" > "$HB.tmp" && mv -f "$HB.tmp" "$HB"
log_json critical enforcer_exhausted max_attempts="$MAX_ATTEMPTS"
exit 1
