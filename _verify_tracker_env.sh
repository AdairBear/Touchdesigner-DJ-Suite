#!/bin/bash
cd /Users/thomasadair/projects/touchdesigner-dj-suite

echo '=== venv python ==='
if [ -f venv/bin/python ]; then
    venv/bin/python --version
    echo '--- key packages ---'
    venv/bin/python - <<'PY'
import importlib, sys
for pkg in ['cv2','mediapipe','pythonosc','numpy']:
    try:
        m = importlib.import_module(pkg)
        v = getattr(m, '__version__', '?')
        print(f'  OK  {pkg}  {v}')
    except Exception as e:
        print(f'  FAIL  {pkg}  -> {e}')
print('python:', sys.version.replace('\n',' '))
PY
else
    echo 'venv/bin/python MISSING'
fi

echo
echo '=== camera check (non-blocking, 2s open/release) ==='
venv/bin/python - <<'PY'
import cv2, time
cap = cv2.VideoCapture(0)
print('opened:', cap.isOpened())
ok, frame = cap.read()
print('read ok:', ok, 'shape:', None if frame is None else frame.shape)
cap.release()
PY

echo
echo '=== existing camera users ==='
ps auxww | grep -E 'TouchDesigner|obs|serato' | grep -v grep | head -5
