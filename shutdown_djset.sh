#!/bin/bash
# shutdown_djset.sh -- clean DJ-set shutdown with NO dialogs.
# Use this to end the show instead of relying on the launcher's quit (which pops
# Serato's "Are you sure?" prompt). Serato reopens fine from a SIGKILL.
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/log_json.sh"
# shellcheck source=lib/kill_tracker.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/kill_tracker.sh"
# shellcheck source=lib/stop_announcer.sh
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/lib/stop_announcer.sh"

# Closure 4 (2026-07-30): this script had NO argument parsing, so the
# `--stop-announcer` the launcher has been passing since the announcer became
# launcher-managed (Sources/AppLauncher.swift) was silently discarded on every
# CLOSE. The launcher believed the announcer was stopped; it was still running.
# A silently ignored flag is worse than either real behaviour, so: parse it, act
# on it, and shout about anything unrecognised rather than swallowing that too.
STOP_ANNOUNCER=0
while [ $# -gt 0 ]; do
    case "$1" in
        --stop-announcer)
            STOP_ANNOUNCER=1
            ;;
        --announcer-port)
            shift
            ANNOUNCER_PORT="$1"
            ;;
        --help|-h)
            echo "usage: shutdown_djset.sh [--stop-announcer] [--announcer-port N]"
            exit 0
            ;;
        *)
            echo "  WARNING: ignoring unrecognised argument '$1'"
            log_json warn unknown_argument argument="$1"
            ;;
    esac
    shift
done

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

# Closure 4: only when the launcher says this session started it. An announcer
# someone else started (a hand-run `python3 -m announcer`, a reinstalled
# LaunchAgent) is not ours to end -- same ownership rule the launcher applies to
# the watchdog agent.
if [ "$STOP_ANNOUNCER" -eq 1 ]; then
    stop_announcer "$ANNOUNCER_PORT"
else
    echo "  leaving serato-obs-announcer alone (no --stop-announcer)"
fi

# Force-kill TD and OBS -- both ignored graceful `quit` under real show
# conditions and needed a manual kill mid-teardown. The canonical-.toe
# workflow means TD's unsaved state is not wanted; an auto-incremented save
# is the file-explosion problem, not a feature.
kill_and_verify "TouchDesigner" "TouchDesigner"
# 2026-08-01 -- OBS gets a GRACEFUL quit first. This is why ACTIVATE was slow.
#
# The chain, measured:
#
#   this script SIGKILLed OBS (pkill -9 -x)
#     -> SIGKILL is an unclean shutdown by definition
#     -> next launch: "[Safe Mode] Unclean shutdown detected!" and a MODAL
#     -> the agent's auto-dismiss ("Run Normally", by button name) needs
#        Accessibility, which it does not have, so nothing clicks it
#     -> OBS blocks on the modal, obs-websocket never loads, :4455 never binds
#     -> the 90s bind and the 180s "OBS never bound its websocket" timeout
#
# 4 of the last 6 OBS logs open with that Safe Mode line, and the most recent
# one contains NOTHING ELSE -- one line, then silence, because OBS is sitting on
# the dialog. So CLOSE was manufacturing the next ACTIVATE's failure.
#
# The old comment here said OBS "ignored graceful quit under real show
# conditions" (07-19), and the -9 was the response. That is still respected: the
# force-kill remains, it just stops being the FIRST move. Give OBS a real chance
# to write its clean-shutdown marker, then take it out if it refuses -- the same
# graceful-then-force shape BUTT already gets for its icecast disconnect.
if pgrep -x "OBS" >/dev/null 2>&1; then
  echo "  asking OBS to quit gracefully (avoids next-launch Safe Mode)..."
  osascript -e 'tell application "OBS" to quit' >/dev/null 2>&1
  obs_clean=0
  for _ in $(seq 1 10); do
    if ! pgrep -x "OBS" >/dev/null 2>&1; then
      echo "  OBS quit cleanly -- next launch will skip Safe Mode"
      log_json info obs_clean_quit
      obs_clean=1
      break
    fi
    sleep 1
  done
  if [ "$obs_clean" -ne 1 ]; then
    echo "  OBS ignored the graceful quit after 10s -- forcing (next launch WILL show Safe Mode)"
    log_json warn obs_force_kill_after_graceful
    kill_and_verify "OBS" "OBS"
  fi
else
  kill_and_verify "OBS" "OBS"
fi

# BUTT stays graceful -- it disconnects from icecast on quit; a SIGKILL can
# leave the mount point held server-side until it times out, breaking the
# *next* show's connect. Do not force-kill this one.
osascript -e 'tell application "BUTT" to quit' 2>/dev/null

# P4: close the start_tracker Terminal window.
osascript -e 'tell application "Terminal" to close (every window whose name contains "start_tracker")' 2>/dev/null

echo "done."
log_json info shutdown_done
