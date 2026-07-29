#!/bin/bash
# shutdown_djset.sh -- clean DJ-set shutdown with NO dialogs.
# Use this to end the show instead of relying on the launcher's quit (which pops
# Serato's "Are you sure?" prompt). Serato reopens fine from a SIGKILL.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/log_json.sh"
# shellcheck source=lib/kill_tracker.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/kill_tracker.sh"
echo "shutting down DJ set (no prompts)..."
log_json info shutdown_start

# SH-1: force-kill + verify. TD and OBS both ignore a graceful `quit` Apple
# Event under real show conditions (osascript exits 0 on delivery, not on the
# app actually quitting -- fail-quiet). pkill -9 + a pgrep poll makes this
# fail-loud instead: if the process is still alive after the kill, we say so.
kill_and_verify() {
  local label="$1" pattern="$2"
  if ! pgrep -x "$pattern" >/dev/null 2>&1; then
    echo "  $label not running"
    log_json info process_not_running process="$label"
    return
  fi
  pkill -9 -x "$pattern" 2>/dev/null
  for _ in 1 2 3; do
    pgrep -x "$pattern" >/dev/null 2>&1 || {
      echo "  killed $label (-9, no prompt)"
      log_json info process_killed process="$label" signal=9
      return
    }
    sleep 1
  done
  echo "  CRITICAL: $label still running 3s after pkill -9 -x \"$pattern\""
  log_json critical process_survived_kill process="$label" signal=9 wait_s=3
}

# P3: force-kill Serato -- bypasses the "Are you sure?" close dialog.
kill_and_verify "Serato DJ Pro" "Serato DJ Pro"

# Stop the OSC tracker + our background helpers.
# Closure 3c (2026-07-29): the tracker line was
# `pkill -f 'python.*movement_tracker.py'`. This is the teardown that runs on
# every CLOSE APP, so it was the highest-traffic instance of the self-match bug
# -- `-f` matches the whole command line, so any shell that merely quoted the
# pattern (an agent session, a terminal running the very command) was in the
# kill set and died with the tracker. Kill by recorded pid; see
# lib/kill_tracker.sh. The two helpers below are the same bug class and are
# knowingly left as-is -- out of Closure 3c's scope, tracked separately.
kill_tracker "movement_tracker"
pkill -f 'perform_enforcer.sh' 2>/dev/null
pkill -f 'serato_placer.sh' 2>/dev/null

# Force-kill TD and OBS -- both ignored graceful `quit` under real show
# conditions and needed a manual kill mid-teardown. The canonical-.toe
# workflow means TD's unsaved state is not wanted; an auto-incremented save
# is the file-explosion problem, not a feature.
kill_and_verify "TouchDesigner" "TouchDesigner"
kill_and_verify "OBS" "OBS"

# BUTT stays graceful -- it disconnects from icecast on quit; a SIGKILL can
# leave the mount point held server-side until it times out, breaking the
# *next* show's connect. Do not force-kill this one.
osascript -e 'tell application "BUTT" to quit' 2>/dev/null

# P4: close the start_tracker Terminal window.
osascript -e 'tell application "Terminal" to close (every window whose name contains "start_tracker")' 2>/dev/null

echo "done."
log_json info shutdown_done
