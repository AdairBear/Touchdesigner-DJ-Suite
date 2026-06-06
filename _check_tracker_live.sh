#!/bin/bash
echo '=== tracker process ==='
ps auxww | grep -E 'movement_tracker' | grep -v grep | head -3
echo
echo '=== mask file ==='
ls -la /tmp/djsam_bodymask.raw 2>&1
echo '=== mask mtime ==='
stat -f '%Sm %z bytes' /tmp/djsam_bodymask.raw 2>&1
echo '=== age in seconds ==='
NOW=$(date +%s); MT=$(stat -f '%m' /tmp/djsam_bodymask.raw 2>/dev/null); if [ -n "$MT" ]; then echo $(( NOW - MT )); else echo 'no mask'; fi
echo
echo '=== last 40 lines of tracker log ==='
tail -40 /Users/thomasadair/projects/touchdesigner-dj-suite/tracker.log 2>&1
echo
echo '=== OSC port 7000 ==='
lsof -iUDP:7000 2>&1 | grep -v NetInfo | head -5
