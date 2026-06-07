#!/usr/bin/env bash
# fix_venv.sh — Rebuilds the Python virtual environment from scratch.
# Clears any path corruption from the old duplicate folder.
#
# Usage:
#   cd /Users/thomasadair/projects/touchdesigner-dj-suite
#   chmod +x fix_venv.sh && ./fix_venv.sh

set -e
cd "$(dirname "$0")"

echo "=== DJ SAM — venv rebuild ==="
echo "Project root: $(pwd)"
echo ""

echo "[1/4] Removing existing venv..."
rm -rf venv
echo "  Done."

echo ""
echo "[2/4] Creating new virtual environment..."
python3 -m venv venv
echo "  Done."

echo ""
echo "[3/4] Activating and installing dependencies..."
source venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt
echo "  Done."

echo ""
echo "[4/4] Verifying key packages..."
python -c "import mediapipe; print('  mediapipe:', mediapipe.__version__)" 2>/dev/null || echo "  mediapipe: not installed (check requirements.txt)"
python -c "import cv2; print('  opencv:', cv2.__version__)" 2>/dev/null || echo "  opencv: not installed"
python -c "from pythonosc import udp_client; print('  python-osc: ok')" 2>/dev/null || echo "  python-osc: not installed"
pytest --version 2>/dev/null || echo "  pytest: not installed"

echo ""
echo "=== venv rebuild complete ==="
echo "To activate: source venv/bin/activate"
