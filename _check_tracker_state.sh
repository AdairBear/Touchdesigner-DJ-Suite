#!/bin/bash
echo '--- movement_tracker procs ---'
ps auxww | grep -E 'movement_tracker|mediapipe|body_mask' | grep -v grep
echo '--- MASK FILE ---'
ls -la /tmp/djsam_bodymask.raw 2>&1
echo '--- MASK MTIME / SIZE ---'
stat -f '%Sm (mtime) %z bytes' /tmp/djsam_bodymask.raw 2>&1
echo '--- NOW ---'
date
echo '--- OSC port 7000 listener ---'
lsof -iUDP:7000 2>&1 | head -10
echo '--- python procs ---'
ps auxww | grep python | grep -v grep | head -10
