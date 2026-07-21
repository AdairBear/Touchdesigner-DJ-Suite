#!/bin/bash
# shutdown_djset.sh -- clean DJ-set shutdown with NO dialogs.
# Use this to end the show instead of relying on the launcher's quit (which pops
# Serato's "Are you sure?" prompt). Serato reopens fine from a SIGKILL.
echo "shutting down DJ set (no prompts)..."

# SH-1: force-kill + verify. TD and OBS both ignore a graceful `quit` Apple
# Event under real show conditions (osascript exits 0 on delivery, not on the
# app actually quitting -- fail-quiet). pkill -9 + a pgrep poll makes this
# fail-loud instead: if the process is still alive after the kill, we say so.
kill_and_verify() {
  local label="$1" pattern="$2"
  if ! pgrep -x "$pattern" >/dev/null 2>&1; then
    echo "  $label not running"
    return
  fi
  pkill -9 -x "$pattern" 2>/dev/null
  for _ in 1 2 3; do
    pgrep -x "$pattern" >/dev/null 2>&1 || { echo "  killed $label (-9, no prompt)"; return; }
    sleep 1
  done
  echo "  CRITICAL: $label still running 3s after pkill -9 -x \"$pattern\""
}

# P3: force-kill Serato -- bypasses the "Are you sure?" close dialog.
kill_and_verify "Serato DJ Pro" "Serato DJ Pro"

# Stop the OSC tracker + our background helpers.
pkill -f 'python.*movement_tracker.py' 2>/dev/null && echo "  killed movement_tracker"
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
