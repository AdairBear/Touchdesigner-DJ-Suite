#!/bin/bash
# serato_placer.sh -- move the Serato DJ Pro window onto the SAMSUNG display.
# Backgrounded by start_tracker.command; waits for Serato's window to exist, then
# positions it on SAMSUNG (found BY NAME via NSScreen, robust to arrangement drift).
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/log_json.sh
source "$REPO/lib/log_json.sh"

LOG=/tmp/serato_placer.log
exec >>"$LOG" 2>&1
echo "==== serato_placer $(date) ===="
log_json info placer_start

# SAMSUNG AppKit top-left origin + size, by NAME (not index).
read SX SY SW SH < <(/usr/bin/swift - <<'SW' 2>/dev/null
import AppKit
let mainH = NSScreen.screens.first(where: { $0.frame.origin == .zero })?.frame.height ?? (NSScreen.main?.frame.height ?? 0)
if let s = NSScreen.screens.first(where: { $0.localizedName.uppercased().contains("SAMSUNG") }) {
    let f = s.frame
    print(Int(f.origin.x), Int(mainH - (f.origin.y + f.height)), Int(f.width), Int(f.height))
}
SW
)
if [ -z "${SX:-}" ]; then
  echo "CRITICAL: SAMSUNG display not found by name -- Serato left where it opened"
  log_json critical display_not_found display=SAMSUNG
  exit 1
fi
echo "SAMSUNG ax=($SX,$SY) ${SW}x${SH}"
log_json info display_found display=SAMSUNG x="$SX" y="$SY" w="$SW" h="$SH"

# Wait for a Serato window to exist (launcher opens Serato a few seconds after us).
for i in $(seq 1 90); do
  wc=$(osascript -e 'tell application "System Events" to tell (first process whose name is "Serato DJ Pro") to count windows' 2>/dev/null)
  if [ "${wc:-0}" -ge 1 ]; then echo "Serato window present after ${i}s"; break; fi
  sleep 1
done

# 2026-08-01: place, then VERIFY, and retry if it did not stick.
#
# Measured on the rig: the placement itself works -- 1713 successful placements,
# 0 "display not found", SAMSUNG resolved by name every time. Two real gaps
# remained:
#
#   1. Serato opens on the MAIN display and stays there until this runs. The
#      log shows "Serato window present after 71s", so there is over a minute
#      where Serato is visibly on the wrong screen during ACTIVATE. That is the
#      "Serato opens on the main screen" symptom.
#   2. The script set the position and declared success without ever reading it
#      back. Serato restores its own window geometry during startup, so a
#      placement made while it is still initialising can be silently overwritten
#      -- and nothing here would have noticed.
#
# So: place, read the position back, confirm the window's centre actually lands
# inside SAMSUNG's rect, and retry a few times if not. Fail loud if it never
# sticks rather than logging "placed" for a window sitting on the wrong screen.
place_once() {
  osascript >/dev/null 2>&1 <<AS
tell application "System Events" to tell process "Serato DJ Pro"
  try
    set position of window 1 to {$SX, $SY}
  end try
  try
    set size of window 1 to {$SW, $SH}
  end try
end tell
AS
}

read_position() {
  osascript -e 'tell application "System Events" to tell process "Serato DJ Pro" to get position of window 1' 2>/dev/null
}

placed_ok=0
for attempt in 1 2 3 4 5; do
  place_once
  sleep 2
  pos=$(read_position)          # "x, y"
  px=$(printf '%s' "$pos" | cut -d, -f1 | tr -d ' ')
  py=$(printf '%s' "$pos" | cut -d, -f2 | tr -d ' ')
  if [ -n "${px:-}" ] && [ -n "${py:-}" ]; then
    # Centre-inside-rect, so a Serato-adjusted size/offset still counts.
    cx=$(( px + SW / 2 ))
    cy=$(( py + SH / 2 ))
    if [ "$cx" -ge "$SX" ] && [ "$cx" -lt $(( SX + SW )) ] \
       && [ "$cy" -ge "$SY" ] && [ "$cy" -lt $(( SY + SH )) ]; then
      echo "placed Serato on SAMSUNG at ($px,$py) -- verified on attempt $attempt"
      log_json info placer_done x="$px" y="$py" attempt="$attempt" verified=true
      placed_ok=1
      break
    fi
  fi
  echo "attempt $attempt: Serato reported at (${px:-?},${py:-?}), not inside SAMSUNG -- retrying"
  sleep 2
done

if [ "$placed_ok" -ne 1 ]; then
  echo "CRITICAL: Serato would not stay on SAMSUNG after 5 attempts (last position: ${pos:-unknown})"
  echo "CRITICAL: it is probably restoring its own window geometry -- move it by hand"
  log_json critical placer_failed last_position="${pos:-unknown}"
fi
