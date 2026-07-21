#!/bin/bash
# shutdown_djset.sh -- clean DJ-set shutdown with NO dialogs.
# Use this to end the show instead of relying on the launcher's quit (which pops
# Serato's "Are you sure?" prompt). Serato reopens fine from a SIGKILL.
echo "shutting down DJ set (no prompts)..."

# P3: force-kill Serato -- bypasses the "Are you sure?" close dialog.
pkill -9 -x "Serato DJ Pro" 2>/dev/null && echo "  killed Serato DJ Pro (-9, no prompt)" || echo "  Serato not running"

# Stop the OSC tracker + our background helpers.
pkill -f 'python.*movement_tracker.py' 2>/dev/null && echo "  killed movement_tracker"
pkill -f 'perform_enforcer.sh' 2>/dev/null
pkill -f 'serato_placer.sh' 2>/dev/null

# Quit the GUI apps that DON'T prompt (leave TD to Thomas if he wants to save).
osascript -e 'tell application "OBS" to quit' 2>/dev/null && echo "  quit OBS"
osascript -e 'tell application "BUTT" to quit' 2>/dev/null

# P4: close the start_tracker Terminal window.
osascript -e 'tell application "Terminal" to close (every window whose name contains "start_tracker")' 2>/dev/null

echo "done."
