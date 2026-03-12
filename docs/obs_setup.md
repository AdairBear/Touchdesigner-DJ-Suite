# OBS Websocket Configuration Guide

## Setup Instructions

### 1. Enable OBS Websocket Server

1. Open **OBS Studio**
2. Go to **Tools** → **WebSocket Server Settings**
3. Check **"Enable WebSocket server"**
4. Note the **Port** (default: `4455`)
5. (Optional) Set a **Password** for security
6. Click **Apply** and **OK**

### 2. Update Python Configuration

If you changed the default settings, update the OBS controller initialization in your code:

```python
from obs_controller import OBSController

controller = OBSController(
    host="localhost",
    port=4455,  # Your OBS websocket port
    password="" # Your password if set
)
```

### 3. Test OBS Connection

Run the OBS controller test:

```bash
python python/obs_controller.py
```

You should see:
```
Connected to OBS at localhost:4455
Current scene: [Your Scene Name]
Stream status: {...}
```

### 4. Available OBS Functions

The OBS controller provides these functions:

```python
# Scene control
controller.get_current_scene()
controller.switch_scene("Scene Name")

# Recording control
controller.start_recording()
controller.stop_recording()

# Source visibility
controller.toggle_source_visibility("Scene Name", "Source Name", True)

# Stream status
status = controller.get_stream_status()
# Returns: {'streaming': bool, 'duration': int, 'bytes': int}
```

### 5. Integration with Movement Tracking

You can automate OBS based on movement:

```python
# Example: Auto-switch scenes based on motion energy
if motion_energy > 80:
    obs_controller.switch_scene("High Energy Scene")
elif motion_energy < 30:
    obs_controller.switch_scene("Calm Scene")
```

### 6. Recommended OBS Setup

**Scene Structure:**
- **Main Scene**: Default performance view
- **Wide Shot**: Full body tracking view
- **Close Up**: Upper body/hands focus
- **Visualizer Only**: Pure TouchDesigner output

**Sources to Control:**
- Webcam feed (show/hide)
- TouchDesigner output (via Spout/NDI)
- Audio visualizer overlays
- Text overlays (track info, etc.)

### 7. Troubleshooting

**Connection Failed:**
- Verify OBS is running
- Check websocket server is enabled in OBS
- Confirm port number matches (default: 4455)
- Test firewall settings

**Authentication Error:**
- Verify password matches OBS settings
- Try without password first for testing

**Commands Not Working:**
- Update obs-websocket-py: `pip install --upgrade obs-websocket-py`
- Check OBS websocket protocol version
- Verify scene/source names match exactly (case-sensitive)

### 8. Spout/NDI Integration

**To send TouchDesigner output to OBS:**

**macOS (Syphon recommended):**
1. In TouchDesigner: Add Syphon Spout Out TOP
2. In OBS: Add "Syphon Client" source
3. Select your TouchDesigner output

**Windows (Spout):**
1. In TouchDesigner: Add Spout Out TOP  
2. In OBS: Install OBS-Spout2-Plugin
3. Add "Spout2 Capture" source

**NDI (Cross-platform):**
1. Install NDI Tools
2. In TouchDesigner: Add NDI Out TOP
3. In OBS: Add "NDI Source"
4. Select your TouchDesigner NDI stream

---

**Status**: Ready for OBS integration
**Websocket Version**: v5 (OBS 28+)
