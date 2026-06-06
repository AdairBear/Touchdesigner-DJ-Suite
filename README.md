# Generative Stream Graphics for Live DJ Performance

Real-time reactive visuals system for Breakbeat Hardcore/Jungle DJ performances (150-180 BPM), combining multi-person movement tracking and audio analysis with TouchDesigner for streaming.

## 🎯 Project Overview

This system provides:
- **Multi-person movement tracking** - MediaPipe pose estimation tracking up to 4 people simultaneously
- **Audio analysis** - Real-time beat detection and frequency analysis (librosa)
- **OBS automation** - Scene control and recording via websocket
- **TouchDesigner integration** - OSC communication for visual generation
- **Live streaming** - Output via Spout/NDI to OBS Studio

## ✨ Key Features

- 🎭 **Multi-Person Tracking**: Track DJ + guests (up to 4 people)
- 🎨 **Color-Coded Visualization**: Each person shown in different color
- 📊 **Per-Person & Global Metrics**: Individual + aggregate motion data
- 🎯 **Optimized for Performance**: Default 2-person mode, expandable to 4

## 🛠 Tech Stack

- **Python 3.10+** - Core development
- **MediaPipe** - Body pose tracking
- **librosa/scipy** - Audio feature extraction
- **python-osc** - Communication with TouchDesigner
- **obs-websocket-py** - OBS Studio automation
- **OpenCV** - Video processing
- **TouchDesigner** - Visual generation (separate component)

## 📁 Project Structure

```
generative-stream-graphics/
├── python/
│   ├── movement_tracker.py      # MediaPipe pose → OSC
│   ├── obs_controller.py        # OBS websocket control
│   └── system_launcher.py       # Orchestration script
├── configs/
│   ├── movement_mappings.json   # Movement → visual mappings
│   └── audio_mappings.json      # Audio → visual mappings
├── tests/
│   ├── test_movement.py
│   └── test_integration.py
├── logs/
│   └── iteration_log.md         # Performance iteration log
├── .vscode/
│   ├── settings.json
│   ├── tasks.json               # VS Code tasks
│   └── snippets.code-snippets   # Iteration logging snippets
├── requirements.txt
└── README.md
```

## 🚀 Quick Start

### 1. Install Dependencies

```bash
# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # On macOS/Linux
# venv\Scripts\activate   # On Windows

# Install requirements
pip install -r requirements.txt
```

### 2. Test Movement Tracking

```bash
# Run movement tracker standalone (default: 2 people)
python python/movement_tracker.py

# Track only 1 person (solo DJ)
# Edit movement_tracker.py: MovementTracker(max_people=1)

# Track up to 4 people
# Edit movement_tracker.py: MovementTracker(max_people=4)
```

This will:
- Open webcam feed with pose overlay
- Track up to 2 people by default (DJ + guest)
- Show each person in different color (Green, Blue, Yellow, Magenta)
- Send OSC messages to localhost:7000
- Display FPS and tracking metrics
- Press ESC to quit

### 3. Launch Full System

```bash
# Use system launcher
python python/system_launcher.py
```

Or use VS Code task: `Cmd+Shift+P` → "Tasks: Run Task" → "Launch Full System"

## 🎛 Configuration

### Movement Mappings (`configs/movement_mappings.json`)

Maps body movements to visual parameters:

```json
{
  "left_hand_height": {
    "target": "particle_spawn_rate",
    "min": 0.0,
    "max": 1.0,
    "multiplier": 5.0,
    "smoothing": 0.1
  }
}
```

### Audio Mappings (`configs/audio_mappings.json`)

Maps audio features to visual parameters:

```json
{
  "bass_rms": {
    "target": "bass_pulse",
    "threshold": 0.2,
    "multiplier": 2.5,
    "attack": 0.01,
    "release": 0.15
  }
}
```

## Body Outline Overlay (edge-confined)

The body overlay is a **thin silhouette outline** — flames (or lightning) ride
the contour line, rather than a filled glow covering the body.

- **Contour at the source.** `movement_tracker.py` extracts a ~1-2 px body
  contour with a morphological gradient (`cv2.morphologyEx(..., MORPH_GRADIENT)`)
  instead of emitting a filled, dilated, Gaussian-blurred silhouette. This is the
  edge-confined primitive the pipeline was missing — every downstream stage is
  then confined to a thin band instead of widening a blob.
- **Why it changed:** see `docs/audits/baseline_outline_audit_2026-06-05.md` (the
  filled+blurred mask was the root cause of the "aura covering the body" look).
- **Instrumentation:** the tracker logs `contour px` ~1x/sec — a thin outline is
  ~0.3-2% of the frame; a blob would be ~25-30%.

### Visual modes: flame / lightning

Switch the outline look live via `configs/visual_mode.json` (`"mode": "flame"` or
`"lightning"`). The tracker broadcasts `/visual/mode` over OSC so a TouchDesigner
Switch TOP can swap shaders without a restart.

- `touchdesigner/shaders/fire_aura.glsl` — flame look (primary)
- `touchdesigner/shaders/lightning.glsl` — electric blue/white, onset-triggered
- Wiring: `docs/setup/visual_mode_toggle.md`

## 🎨 TouchDesigner Integration

The system sends OSC messages to TouchDesigner (default: `localhost:7000`).

### 🆕 Generative Visual Control (NEW!)

**AI-driven generative visual control is now available!** The system can control:
- Geometry types (particles, sphere, fractals, mesh)
- Shader color palettes (theme-based hex colors)
- Visual effects (particle bursts, flashes, pulses)
- Audio-visual sync mappings (bass → particles, etc.)
- Arbitrary parameter control (any TouchDesigner parameter)

**📖 Get Started:** See **[QUICKSTART_OSC_INTEGRATION.md](QUICKSTART_OSC_INTEGRATION.md)** for 3-step implementation guide.

**Documentation:**
- [Quick Start Guide](QUICKSTART_OSC_INTEGRATION.md) - Start here!
- [Implementation Checklist](GENERATIVE_OSC_CHECKLIST.md) - Step-by-step TouchDesigner setup
- [DAT Scripts](TOUCHDESIGNER_DAT_SCRIPTS.md) - Copy-paste Python scripts for TouchDesigner
- [Technical Deep-Dive](docs/GENERATIVE_OSC_SETUP.md) - Full OSC architecture details
- [Test Suite](test_td_osc_integration.py) - Automated testing script

---

### Multi-Person Movement Messages

Each person gets their own OSC namespace:

**Person 1 (DJ):**
- `/movement/person1/left_hand_height` - Left hand vertical position
- `/movement/person1/right_hand_height` - Right hand vertical position
- `/movement/person1/hand_spread` - Distance between hands
- `/movement/person1/motion_energy` - Motion intensity
- `/movement/person1/body_height` - Body center vertical position
- `/movement/person1/tracking_active` - Tracking status (1.0 = active)

**Person 2, 3, 4...** (same structure with `/movement/person2/...`, etc.)

**Global Statistics:**
- `/movement/num_people` - Number of people currently tracked
- `/movement/avg_energy` - Average motion energy across all people

### Audio Messages (Future)
- `/audio/bass_rms` - Bass energy
- `/audio/onset_strength` - Beat detection
- `/audio/break_complexity` - Drum pattern complexity

## 📊 Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Movement FPS | 25-30 | Pose tracking frame rate (multi-person) |
| Audio Latency | <50ms | Beat → visual response time |
| Movement Latency | <100ms | Gesture → visual response time |
| Tracking Accuracy | 90%+ | MediaPipe confidence |
| CPU Usage | <70% | Python components (2-person mode) |
| Render FPS | 60 | TouchDesigner output |

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Test movement tracking
python python/movement_tracker.py
```

### Manual Test Scenarios

**Movement:**
- Standing still
- Arm raise on drop
- Dancing to beat
- Rapid hand movements
- Big gesture on drop

**Audio:**
- Amen roller (160 BPM)
- Reese bassline
- Ragga jungle
- Minimal tech-step
- Double drop

## 🎮 VS Code Tasks

Configured tasks (Run with `Cmd+Shift+P` → "Tasks: Run Task"):

1. **Launch Full System** - Start all components
2. **Test Movement Tracking** - Test pose tracking only
3. **Run All Tests** - Execute pytest suite
4. **Install Dependencies** - Install from requirements.txt

## 📝 Iteration Logging

Use VS Code snippets for systematic performance iteration:

1. Type `itlog` in markdown file → Create iteration log entry
2. Type `perftest` → Log performance test results

Logs stored in `logs/iteration_log.md`

## 🔧 Troubleshooting

### Camera Not Detected
```bash
# Check camera availability (macOS)
system_profiler SPCameraDataType

# Test with OpenCV
python -c "import cv2; print(cv2.VideoCapture(0).isOpened())"
```

### OBS Websocket Connection Failed
1. Open OBS Studio
2. Tools → WebSocket Server Settings
3. Enable WebSocket server
4. Note port (default: 4455) and password

### MediaPipe Installation Issues (macOS)
```bash
# If mediapipe fails to install
pip install --upgrade pip
pip install mediapipe --no-cache-dir
```

## 🎵 BPM-Specific Optimizations

System optimized for **Breakbeat Hardcore/Jungle (150-180 BPM)**:

- Fast breakbeat detection (16th note rolls)
- Sub-bass frequency tracking (40-80 Hz)
- Rapid onset detection for drum hits
- High-frequency hi-hat tracking
- Double-drop synchronization

## 🔗 Integration Flow

```
Serato DJ (Audio) ──────────┐
                            │
Webcam (Movement) → MediaPipe → Python Scripts → OSC → TouchDesigner → Spout/NDI → OBS Studio → Stream
                            │
                    OBS Websocket ←─────────────────────────────────────┘
```

## 📜 License

This project is for personal live performance use. See individual library licenses for dependencies.

## 🎤 Credits

Created for live Breakbeat Hardcore/Jungle DJ performances
Optimized for 150-180 BPM jungle breaks and Reese basslines

---

**Status**: Active Development
**Last Updated**: December 28, 2025
