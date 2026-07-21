#!/bin/bash
# DJ Sam body tracker launcher
# Launches movement_tracker.py from the project venv.
# Terminal has camera permission on this Mac; Python inherits it from Terminal.
#
# Double-click this file (or `open` it) to start the tracker.
# Logs go to tracker.log in the project root.

PROJECT_DIR="/Users/thomasadair/projects/touchdesigner-dj-suite"
cd "$PROJECT_DIR" || { echo "Cannot cd to $PROJECT_DIR"; exit 1; }

# shellcheck source=lib/log_json.sh
source "$PROJECT_DIR/lib/log_json.sh"

LOG="$PROJECT_DIR/tracker.log"

echo "---- starting body tracker $(date) ----"
echo "Project: $PROJECT_DIR"
echo "Python:  $PROJECT_DIR/venv/bin/python"
echo "Log:     $LOG"
echo
log_json info tracker_start

# Kill any existing tracker so we don't double up on the camera.
pkill -f 'python.*movement_tracker.py' 2>/dev/null && echo 'killed previous tracker' || true
sleep 1

# --- Perform Mode enforcer (background) ----------------------------------
# The launcher runs THIS script right before it opens the .toe. Launch the
# external Perform Mode enforcer in the background: it waits for TD to come up,
# forces Perform Mode on the HISENSE via the Textport, VERIFIES it took (retries
# until confirmed), and fails LOUD (CRITICAL heartbeat) if it can't. This does
# NOT depend on TD's racy internal performOnStart -- it's the reliable layer.
# Dev opt-out: `touch /tmp/td_no_autoperform` before launching. See RUNBOOK below
# and PERFORM_MODE_SETUP.md.
nohup bash "$PROJECT_DIR/perform_enforcer.sh" >/dev/null 2>&1 &
echo 'launched Perform Mode enforcer in background (log: /tmp/perform_enforcer.log)'

# --- Serato -> SAMSUNG display (background) -------------------------------
# Waits for Serato's window (the launcher opens it a few seconds after this
# script) and moves it onto the SAMSUNG display (by name). See /tmp/serato_placer.log.
nohup bash "$PROJECT_DIR/serato_placer.sh" >/dev/null 2>&1 &
echo 'launched Serato->SAMSUNG placer in background (log: /tmp/serato_placer.log)'

# --max-people 1 (solo DJ), default camera 0, default OSC 127.0.0.1:7000.
# Preview window ENABLED (--no-preview removed) per Thomas's request 2026-07-17.
# To go headless again for the actual show, add a "    --no-preview \" line
# back into the continuation below, right after "--max-people 1 \".
# NOTE: no `exec` -- we want the shell to survive the tracker so the trailing
# line runs when the tracker is killed on shutdown (closes this Terminal window).
venv/bin/python python/movement_tracker.py \
    --max-people 1 \
    2>&1 | tee -a "$LOG"

log_json info tracker_exit exit_code="${PIPESTATUS[0]}"

# P4: tracker has exited (killed on shutdown) -> close this Terminal window so it
# doesn't linger after the set. Backgrounded so it can close its own parent window.
osascript -e 'tell application "Terminal" to close (every window whose name contains "start_tracker")' >/dev/null 2>&1 &
