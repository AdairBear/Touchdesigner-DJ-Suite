# Setup Complete - Next Steps

## ✅ Completed Setup Steps

### 1. Python 3.11 Environment ✓
- Installed Python 3.11 via Homebrew
- Created virtual environment: `venv/`
- Installed all core dependencies (MediaPipe, OpenCV, OSC, etc.)
- **Note**: Librosa (audio analysis) excluded due to llvmlite compilation issues

### 2. VS Code Configuration ✓
- Python interpreter configured to use venv
- Tasks configured for easy launching
- Code snippets ready for iteration logging

### 3. Movement Tracking Ready ✓
- MediaPipe installed and configured
- Movement tracker script ready to run
- **Camera permissions may be required on first run**

### 4. TouchDesigner OSC Configuration ✓
- Documented in [`docs/touchdesigner_setup.md`](docs/touchdesigner_setup.md)
- OSC port: 7000
- All movement channels mapped

### 5. OBS Websocket Configuration ✓
- Documented in [`docs/obs_setup.md`](docs/obs_setup.md)
- Default port: 4455
- Scene control ready

---

## 🚀 Quick Start Commands

### Run Movement Tracker
```bash
# Using VS Code task
Cmd+Shift+P → "Tasks: Run Task" → "Test Movement Tracking"

# Or via terminal
source venv/bin/activate
python python/movement_tracker.py
```

**First run**: You'll need to grant camera permissions:
- System Settings → Privacy & Security → Camera
- Enable for Terminal or VS Code

### Launch Full System
```bash
# Using VS Code task
Cmd+Shift+P → "Tasks: Run Task" → "Launch Full System"

# Or via terminal
source venv/bin/activate
python python/system_launcher.py
```

### Test OBS Connection
```bash
source venv/bin/activate
python python/obs_controller.py
```

---

## 📝 Configuration Files

### Movement Mappings
Edit [`configs/movement_mappings.json`](configs/movement_mappings.json) to adjust:
- Parameter ranges (min/max)
- Multipliers for sensitivity
- Smoothing values

### OBS/TouchDesigner Settings
- Movement tracker: Default OSC to `localhost:7000`
- OBS controller: Default websocket to `localhost:4455`
- Modify in Python files if needed

---

## 🎬 Recommended Workflow

1. **Start TouchDesigner** with OSC In CHOP configured (port 7000)
2. **Start OBS** with websocket enabled (port 4455)
3. **Run movement tracker** or full system launcher
4. **Test tracking** - wave hands, check OSC data in TouchDesigner
5. **Map parameters** - connect OSC channels to visual effects
6. **Iterate and log** - use `itlog` snippet in markdown files

---

## ⚠️ Known Limitations

### Audio Analysis Not Included
- Librosa requires llvmlite which has compilation issues
- Alternative: Use TouchDesigner's Audio Analysis TOP for beat detection
- Or install librosa manually later with conda if needed

### Camera Access
- macOS requires camera permissions for Python/Terminal
- First run will prompt for permission
- Grant in System Settings → Privacy & Security

---

## 📊 Performance Targets

| Metric | Target | How to Check |
|--------|--------|--------------|
| Movement FPS | 30+ | Shown in tracker window |
| Camera Latency | <100ms | Visual feedback test |
| OSC Latency | <50ms | TouchDesigner response |
| CPU Usage | <60% | Activity Monitor |

---

## 🔧 Troubleshooting

### Movement Tracker Won't Start
```bash
# Check camera availability
python -c "import cv2; cap = cv2.VideoCapture(0); print(cap.isOpened()); cap.release()"

# Check MediaPipe installation
python -c "import mediapipe; print(mediapipe.__version__)"
```

### OSC Not Received in TouchDesigner
```bash
# Check if port 7000 is available
lsof -i :7000

# Test OSC sending
python -c "from pythonosc import udp_client; c = udp_client.SimpleUDPClient('127.0.0.1', 7000); c.send_message('/test', 1.0); print('Sent')"
```

### OBS Connection Failed
1. Verify OBS is running
2. Tools → WebSocket Server Settings → Enable
3. Check port matches (default: 4455)

---

## 📚 Documentation

- [TouchDesigner OSC Setup](docs/touchdesigner_setup.md)
- [OBS Websocket Setup](docs/obs_setup.md)
- [Full README](README.md)
- [Installation Notes](INSTALL.md)

---

## 🎵 Ready to DJ!

Your Generative Stream Graphics system is ready for live performance. Start with movement tracking, then add TouchDesigner visuals, and finally integrate OBS for streaming.

**Pro tip**: Use the iteration log snippets (`itlog` and `perftest`) to track your tuning process systematically!

---

**Setup Date**: December 28, 2025
**Python Version**: 3.11.14
**Status**: ✅ Ready for Performance
