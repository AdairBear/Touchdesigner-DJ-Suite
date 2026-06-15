#!/bin/bash
# Touchdesigner DJ Suite body tracker launcher
# Launches movement_tracker.py from the project venv.
# Terminal has camera permission on this Mac; Python inherits it from Terminal.
#
# Double-click this file (or `open` it) to start the tracker.
# Logs go to tracker.log in the project root.

PROJECT_DIR="/Users/thomasadair/projects/touchdesigner-dj-suite"
cd "$PROJECT_DIR" || { echo "Cannot cd to $PROJECT_DIR"; exit 1; }

LOG="$PROJECT_DIR/tracker.log"

echo "---- starting body tracker $(date) ----"
echo "Project: $PROJECT_DIR"
echo "Python:  $PROJECT_DIR/venv/bin/python"
echo "Log:     $LOG"
echo

# Kill any existing tracker so we don't double up on the camera.
pkill -f 'python.*movement_tracker.py' 2>/dev/null && echo 'killed previous tracker' || true
sleep 1

# Run with --no-preview so we don't add a cv2 window during the stream,
# --max-people 1 (solo DJ), default camera 0, default OSC 127.0.0.1:7000.
exec venv/bin/python python/movement_tracker.py \
    --max-people 1 \
    --no-preview \
    2>&1 | tee -a "$LOG"
