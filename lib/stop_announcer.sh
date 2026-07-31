#!/bin/bash
# Stop serato-obs-announcer by PORT OWNER -- never by argv substring.
#
# Closure 4 (2026-07-30). Two things converged to make this necessary:
#
#   1. `shutdown_djset.sh` accepted `--stop-announcer` from the launcher
#      (Sources/AppLauncher.swift passes it whenever this session started the
#      announcer) and SILENTLY DISCARDED IT. The script had no argument parsing
#      at all. So CLOSE believed it had stopped the announcer and the announcer
#      kept running -- one of the two named zombie cases behind the 2026-07-28
#      gap report's "State 3: FAILS" verdict.
#   2. The announcer's LaunchAgent was retired 2026-07-30 (bootout + plist
#      removed). It used to be `KeepAlive=1`, which is why nobody had built a
#      working stop: launchd would just restart it. Now nothing does, so CLOSE
#      genuinely owns the process and has to be able to end it.
#
# **Why the port and not the process name.** The old kill shape everywhere in
# this suite was `pkill -f -- "-m announcer"`. `-f` matches the whole command
# line, so any shell or editor whose own argv quoted that string was in the kill
# set -- the Closure 3c defect, which produced phantom PIDs on the kill path.
# There is no clean exact-name to match instead: the process is `python3`, and
# killing every python3 on the box is obviously wrong. But the announcer is
# defined by the thing that makes it useful -- it serves OBS's browser source on
# :17900. Whoever holds that port IS the announcer. That is provenance a
# substring match cannot fake, and it is the same rule the Swift launcher uses
# to find the watchdog agent (Sources/AgentTeardown.swift).
#
# Mirrors lib/kill_tracker.sh in shape: TERM, verify, escalate, verify, and say
# so loudly if the process outlives the kill.

ANNOUNCER_PORT="${SERATO_ANNOUNCER_PORT:-17900}"

# stop_announcer [port] -- always returns 0; teardown must continue regardless.
stop_announcer() {
    local port="${1:-$ANNOUNCER_PORT}" pids survivors rebound

    pids=$(lsof -ti :"$port" 2>/dev/null | tr '\n' ' ')
    pids="${pids% }"
    if [ -z "$pids" ]; then
        echo "  serato-obs-announcer not running (nothing listening on :$port)"
        log_json info announcer_not_running port="$port"
        return 0
    fi

    # TERM first: the announcer holds an OBS browser-source connection and a
    # Serato library file handle, and a clean exit closes both.
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null
    for _ in 1 2 3; do
        survivors=$(lsof -ti :"$port" 2>/dev/null | tr '\n' ' ')
        if [ -z "${survivors// /}" ]; then
            echo "  stopped serato-obs-announcer (pid(s) $pids, SIGTERM, :$port free)"
            log_json info announcer_stopped port="$port" pids="$pids" signal=15
            return 0
        fi
        sleep 1
    done

    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null
    sleep 1
    survivors=$(lsof -ti :"$port" 2>/dev/null | tr '\n' ' ')
    if [ -z "${survivors// /}" ]; then
        echo "  stopped serato-obs-announcer (pid(s) $pids, SIGKILL, :$port free)"
        log_json info announcer_stopped port="$port" pids="$pids" signal=9
        return 0
    fi

    # Still held after SIGKILL means something is *re-creating* it -- almost
    # certainly a LaunchAgent that got reinstalled. Name that possibility in the
    # message: "it survived" sends someone hunting the wrong thing.
    rebound="${survivors// /}"
    echo "  CRITICAL: :$port still held after SIGKILL (pid(s) $survivors)."
    echo "  CRITICAL: if the pid changed, something is restarting it — check"
    echo "  CRITICAL:   launchctl list | grep serato-obs-announcer"
    log_json critical announcer_survived_kill port="$port" pids="$pids" \
        survivors="$rebound" signal=9
    return 0
}
