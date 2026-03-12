# Installation Notes

## Python Environment Setup

**Date**: December 28, 2025
**Python Version**: 3.14.2
**Architecture**: i386

### Important: MediaPipe Compatibility

MediaPipe currently has limited support for Python 3.14 and may not have pre-built wheels available. 

### Recommended Setup Options

#### Option 1: Use Python 3.10-3.11 (Recommended)
MediaPipe officially supports Python 3.8-3.11. Install Python 3.10 or 3.11:

```bash
# Using Homebrew on macOS
brew install python@3.11

# Create virtual environment with Python 3.11
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Option 2: Install Dependencies Individually

Try installing packages one at a time to identify which ones work:

```bash
pip install opencv-python
pip install numpy
pip install python-osc
pip install scipy
pip install pandas
pip install pytest

# MediaPipe - may need specific version
pip install mediapipe==0.10.9  # Try latest stable

# obs-websocket-py
pip install obs-websocket-py

# librosa - may need conda
pip install librosa
```

#### Option 3: Use Conda Environment

```bash
# Create conda environment with Python 3.10
conda create -n dj-visuals python=3.10
conda activate dj-visuals

# Install packages
pip install -r requirements.txt
```

### Next Steps

1. Set up Python 3.10 or 3.11 environment
2. Update VS Code Python interpreter path in [.vscode/settings.json](.vscode/settings.json)
3. Install dependencies
4. Test movement tracker

### Camera Permissions (macOS)

You'll need to grant camera access:
1. System Settings → Privacy & Security → Camera
2. Enable for Terminal/VS Code/Python

---

For now, the project structure is complete. Install dependencies with a compatible Python version before running.
