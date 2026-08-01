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
# shellcheck source=lib/kill_tracker.sh
source "$PROJECT_DIR/lib/kill_tracker.sh"   # kill_tracker(), $TRACKER_PID_FILE

LOG="$PROJECT_DIR/tracker.log"

echo "---- starting body tracker $(date) ----"
echo "Project: $PROJECT_DIR"
echo "Python:  $PROJECT_DIR/venv/bin/python"
echo "Log:     $LOG"
echo
log_json info tracker_start

# ---------------------------------------------------------------------------
# ATOMIC SINGLE-START LOCK (2026-08-01)
#
# Two trackers were starting ~1s apart on the live rig:
#
#     14:15:46,059  Seqlock mask buffers ready
#     14:15:47,018  Seqlock mask buffers ready
#
# The ACTIVATE sequencer starts the tracker as stage 1; the agent's poll loop
# runs concurrently and, during the tracker's ~82s warmup, sees "not running"
# and fires tracker_respawn -- a second invocation of THIS script. Both then
# reached `kill_tracker` before either had written /tmp/.tracker_pid, so each
# saw no predecessor, killed nothing, and started a tracker.
#
# The dedup logic was never wrong; it was not ATOMIC. `mkdir` is atomic on
# POSIX -- exactly one concurrent caller can create the directory -- so it is
# the lock primitive here rather than a check-then-write on a file, which is
# the same race one level down.
#
# Two trackers is not cosmetic: they contend for the single camera (the loser
# is refused and dies) and both mmap and write the SAME seqlock buffers, which
# assume ONE writer. Interleaved writers can hand TD a torn frame and a
# non-monotonic counter.
#
# The agent-side guards (remediation/tracker_respawn.py) close the known
# invoker. This closes the race for ANY caller, at source.
LOCKDIR="/tmp/.tracker_start.lock"
LOCK_STALE_S=300   # tracker warmup is ~82s; 300s means a crashed run cannot wedge us

if ! mkdir "$LOCKDIR" 2>/dev/null; then
  lock_age=$(( $(date +%s) - $(stat -f %m "$LOCKDIR" 2>/dev/null || date +%s) ))
  if [ "$lock_age" -gt "$LOCK_STALE_S" ]; then
    echo "stale start-lock ($lock_age s old) -- taking it over"
    log_json warn tracker_start_lock_stale age_s="$lock_age"
    rmdir "$LOCKDIR" 2>/dev/null
    mkdir "$LOCKDIR" 2>/dev/null || true
  else
    # Someone else is mid-start, or a tracker is already up. Either way this
    # invocation must NOT add a second one. Exit 0: declining is the correct
    # outcome, not an error.
    if [ -f "$TRACKER_PID_FILE" ] \
       && ps -p "$(cat "$TRACKER_PID_FILE" 2>/dev/null)" -o command= 2>/dev/null \
          | grep -q '/movement_tracker\.py'; then
      echo "a tracker is already running (pid $(cat "$TRACKER_PID_FILE")) -- nothing to do"
      log_json info tracker_start_skipped reason=already_running
    else
      echo "another start_tracker.command is starting a tracker right now -- standing down"
      log_json info tracker_start_skipped reason=concurrent_start
    fi
    exit 0
  fi
fi
# Held for this script's lifetime, which is the tracker's lifetime (the tracker
# runs in the foreground pipeline below). So while a tracker is alive the lock
# is held, and a later invocation takes the "already running" branch above --
# which is exactly the idempotency we want. When the tracker dies this script
# exits, the trap frees the lock, and a genuine respawn can proceed.
trap 'rmdir "$LOCKDIR" 2>/dev/null' EXIT

# IDEMPOTENCY: even holding the lock, do nothing if a healthy tracker exists.
# Covers the sequential case (A finishes, B starts a second later) that the
# lock alone would serialise into a needless kill-and-restart.
if [ -f "$TRACKER_PID_FILE" ] \
   && ps -p "$(cat "$TRACKER_PID_FILE" 2>/dev/null)" -o command= 2>/dev/null \
      | grep -q '/movement_tracker\.py'; then
  echo "tracker already running (pid $(cat "$TRACKER_PID_FILE")) -- not starting a second"
  log_json info tracker_start_skipped reason=already_running_locked
  exit 0
fi
# ---------------------------------------------------------------------------

# Kill any existing tracker so we don't double up on the camera.
# Closure 3c (2026-07-29): this was `pkill -f 'python.*movement_tracker.py'`,
# which matched the command line of any shell that merely quoted the pattern
# and killed it. Kill by the recorded pid instead -- see lib/kill_tracker.sh.
kill_tracker "previous tracker"
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
#
# Closure 3c: record the tracker's REAL pid so nothing downstream (this script's
# own kill above, agent/remediation/seqlock_stall.py, the launcher's teardown)
# ever has to substring-match a command line again. The wrapper writes its own
# $$ and then `exec`s the tracker, so the recorded pid IS the python process --
# and because exec keeps the pipeline in the foreground, ${PIPESTATUS[0]} below
# is still the tracker's exit code. `$$` inside `sh -c` is that sh's own pid
# (bash 3.2 has no $BASHPID, which is why this isn't a plain subshell).
sh -c 'echo $$ > "$1"; shift; exec "$@"' _ "$TRACKER_PID_FILE" \
    venv/bin/python python/movement_tracker.py \
    --max-people 1 \
    2>&1 | tee -a "$LOG"

# Deliberately NOT unlinking $TRACKER_PID_FILE here. A newer run of this script
# may already own it, and every reader (kill_previous_tracker above,
# agent/tracker_pid.py) re-validates the pid against `ps` before acting on it,
# so a stale file is inert by design -- whereas racing to delete someone else's
# record would send the next kill down the argv-scan fallback for no reason.
log_json info tracker_exit exit_code="${PIPESTATUS[0]}"

# P4: tracker has exited (killed on shutdown) -> close this Terminal window so it
# doesn't linger after the set. Backgrounded so it can close its own parent window.
osascript -e 'tell application "Terminal" to close (every window whose name contains "start_tracker")' >/dev/null 2>&1 &
