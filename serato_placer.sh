#!/bin/bash
# serato_placer.sh -- move the Serato DJ Pro window onto the SAMSUNG display.
# Backgrounded by start_tracker.command; waits for Serato's window to exist, then
# positions it on SAMSUNG (found BY NAME via NSScreen, robust to arrangement drift).
LOG=/tmp/serato_placer.log
exec >>"$LOG" 2>&1
echo "==== serato_placer $(date) ===="

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
  exit 1
fi
echo "SAMSUNG ax=($SX,$SY) ${SW}x${SH}"

# Wait for a Serato window to exist (launcher opens Serato a few seconds after us).
for i in $(seq 1 90); do
  wc=$(osascript -e 'tell application "System Events" to tell (first process whose name is "Serato DJ Pro") to count windows' 2>/dev/null)
  if [ "${wc:-0}" -ge 1 ]; then echo "Serato window present after ${i}s"; break; fi
  sleep 1
done

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
echo "placed Serato on SAMSUNG at ($SX,$SY)"
