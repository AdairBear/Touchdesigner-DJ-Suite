#!/bin/bash
# Kill the body tracker by recorded PID -- never by argv substring.
#
# Closure 3c (2026-07-29). Every kill path here used to be
#   pkill -f 'python.*movement_tracker.py'
# `-f` matches the WHOLE COMMAND LINE of every process on the box, and any
# shell running as `zsh -c "pkill -f 'python.*movement_tracker.py'"` carries
# that string in its own command line. So the kill matched the shell that
# issued it, and every sibling terminal / editor / agent session that merely
# mentioned the pattern went with it. That is what was killing Terminal
# windows mid-command (exit 144) during the Closure 3b verification run.
#
# start_tracker.command -- the single spawner for every path that starts the
# tracker -- records the tracker's real pid in $TRACKER_PID_FILE. Kill that
# pid, after re-confirming via `ps` that it is still the tracker, so a stale
# file or a recycled pid can never aim the kill at a bystander.
#
# The fallback scan runs only when there is no usable pid file (e.g. a tracker
# started before this change). It matches on argv SHAPE, which a shell command
# line cannot satisfy: argv[0] must itself be a python binary AND a later token
# must be a *path* ending in /movement_tracker.py. That rejects both
#   zsh -c "pkill -f 'python.*movement_tracker.py'"     (argv[0] is a shell)
#   python -c 'print("... movement_tracker.py ...")'    (token has no slash)
# It is still a heuristic; the pid file is the real answer.
#
# Mirrored in Python at td-dj-launcher/agent/tracker_pid.py -- keep the two in
# sync if the tracker's launch shape ever changes.

TRACKER_PID_FILE="${TRACKER_PID_FILE:-/tmp/.tracker_pid}"

# kill_tracker [label] -- echoes what it killed; always returns 0.
kill_tracker() {
    local label="${1:-previous tracker}" pid stale

    if [ -f "$TRACKER_PID_FILE" ]; then
        pid=$(cat "$TRACKER_PID_FILE" 2>/dev/null)
        if [ -n "$pid" ] && ps -p "$pid" -o command= 2>/dev/null | grep -q '/movement_tracker\.py'; then
            kill -9 "$pid" 2>/dev/null && echo "  killed $label (pid $pid, from $TRACKER_PID_FILE)"
            rm -f "$TRACKER_PID_FILE"
            return 0
        fi
        rm -f "$TRACKER_PID_FILE"
    fi

    stale=$(ps -Ao pid=,command= | awk -v self="$$" '
        $1 != self && $2 ~ /(^|\/)[Pp]ython[0-9.]*$/ {
            for (i = 3; i <= NF; i++) if ($i ~ /\/movement_tracker\.py$/) { print $1; break }
        }')
    if [ -n "$stale" ]; then
        echo "$stale" | while read -r pid; do
            kill -9 "$pid" 2>/dev/null && echo "  killed $label (pid $pid, argv-shape scan)"
        done
    fi
    return 0
}
