# TouchDesigner Generative OSC - Implementation Checklist

**Goal:** Add AI-driven generative visual control to dj_visuals.toe

**Time Estimate:** 30-45 minutes

**✨ NEW RESOURCES CREATED:**
- 📄 **[TOUCHDESIGNER_DAT_SCRIPTS.md](TOUCHDESIGNER_DAT_SCRIPTS.md)** - All 6 Python DAT scripts ready to copy-paste
- 🧪 **[test_td_osc_integration.py](test_td_osc_integration.py)** - Automated OSC test suite with 7 scenarios

---

## Prerequisites

- [ ] Read [TOUCHDESIGNER_DAT_SCRIPTS.md](TOUCHDESIGNER_DAT_SCRIPTS.md) for all DAT scripts
- [ ] Read [docs/GENERATIVE_OSC_SETUP.md](docs/GENERATIVE_OSC_SETUP.md) for full technical details
- [ ] Open `dj_visuals.toe` in TouchDesigner
- [ ] Verify existing OSC In on port 7000 is working

---

## Implementation Steps

### 1. Add OSC In CHOP for Generative Commands (5 min)

- [ ] Add **OSC In CHOP** operator
- [ ] Rename to: `osc_generative`
- [ ] Configure parameters:
  - Network Address: `127.0.0.1`
  - Port: `7000`
  - Protocol: `UDP`
  - Filter: `/td/gen/*`
- [ ] Test by sending: `python -c "from pythonosc import udp_client; c = udp_client.SimpleUDPClient('127.0.0.1', 7000); c.send_message('/td/gen/test', 1.0)"`

### 2. Create Geometry Switcher (10 min)

- [ ] Add **Select CHOP** → pattern: `/td/gen/geometry/type`
- [ ] Add **CHOP Execute DAT** to the Select CHOP
- [ ] Copy geometry switcher code from docs (Step 2)
- [ ] Create **Switch TOP** named `geo_switch`
- [ ] Create or identify container `geo_container` with:
  - `particle_top` (particle system)
  - `sphere_sop` (sphere geometry)
  - `fractal_top` (fractal generator)
  - `mesh_sop` (mesh geometry)
- [ ] Test: Send `/td/gen/geometry/type` with value "particles", "sphere", "fractals", or "mesh"

### 3. Implement Shader Palette System (10 min)

- [ ] Add **Select CHOP** → pattern: `/td/gen/shader/palette/*`
- [ ] Add **CHOP Execute DAT** with palette code from docs (Step 3)
- [ ] Create **Constant TOPs** named:
  - `constant_color0`
  - `constant_color1`
- [ ] Create **CHOP** named `shader_intensity`
- [ ] Test: Send palette with hex colors (e.g., `#FF0000`, `#0000FF`)

### 4. Add Effect Trigger System (10 min)

- [ ] Add **Select CHOP** → pattern: `/td/gen/effect/*`
- [ ] Add **CHOP Execute DAT** with effect trigger code from docs (Step 4)
- [ ] Identify or create effect operators:
  - `particle_emit` (for particle_burst effect)
  - `flash_level` (for flash effect)
  - `geo_scale` (for pulse effect)
- [ ] Test: Send `/td/gen/effect/particle_burst/trigger 1` with `/td/gen/effect/particle_burst/duration 2.0`

### 5. Create Sync Mapping System (10 min)

- [ ] Add **Table DAT** named `sync_map` with columns:
  - `audio_feature`
  - `visual_param`
  - `curve`
  - `multiplier`
- [ ] Add **CHOP Execute DAT** with sync mapping code from docs (Step 5)
- [ ] Add **Timer CHOP** to periodically apply mappings
- [ ] Add **Python CHOP/SOP** with `apply_sync_mappings()` function
- [ ] Test: Send `/td/gen/sync/bass_rms/target particle_spawn_rate`

### 6. Add Arbitrary Parameter Control (5 min)

- [ ] Add **CHOP Execute DAT** with parameter control code from docs (Step 6)
- [ ] Test: Send `/td/gen/param/noise1/amplitude 0.5` to control any parameter

---

## Testing with Automated Test Suite

**Recommended:** Use the comprehensive test script to verify all OSC integration:

```bash
cd /Users/thomasadair/projects/touchdesigner-dj-suite
python test_td_osc_integration.py
```

The test script runs 7 scenarios:
1. **Geometry Control** - Cycles through particles, sphere, fractals, mesh
2. **Shader Palette** - Tests 3 color themes (jungle, techno, happy hardcore)
3. **Background Color** - Sets black, dark gray, dark blue backgrounds
4. **Effect Triggers** - Fires particle_burst, flash, pulse effects
5. **Sync Mappings** - Creates bass_rms, onset_strength, high_freq mappings
6. **Parameter Control** - Updates noise amplitude, rotation speed, blur
7. **Full Composition** - Simulates complete jungle track with all features

**Expected Results:**
- Geometry switches between types every 2 seconds
- Colors change to red/black, blue/cyan, purple/pink themes
- Flash effects visible every few seconds
- Console shows DAT print statements confirming OSC received
- No Python errors in TouchDesigner textport (Alt+T)

---

## Testing with AV Composer

Once automated tests pass, connect to real orchestrator:

```bash
cd /Users/thomasadair/projects/av-composer
python demo_pattern_workflow.py
```

Expected behavior:
1. Geometry switches to "particles"
2. Shader colors change to jungle theme (red/black)
3. Bass sync mapping activates
4. Particle burst effect triggers on composition start

---

## Quick Manual Test Commands

For individual feature testing, use Python console:

```python
from pythonosc import udp_client

client = udp_client.SimpleUDPClient("127.0.0.1", 7000)

# Test geometry
client.send_message("/td/gen/geometry/type", "particles")

# Test palette
client.send_message("/td/gen/shader/palette/color0", "#FF0000")
client.send_message("/td/gen/shader/palette/color1", "#000000")
client.send_message("/td/gen/shader/palette/intensity", 0.9)

# Test effect
client.send_message("/td/gen/effect/flash/trigger", 1)
client.send_message("/td/gen/effect/flash/duration", 0.5)

# Test sync
client.send_message("/td/gen/sync/bass_rms/target", "particle_spawn_rate")
client.send_message("/td/gen/sync/bass_rms/curve", "exponential")
client.send_message("/td/gen/sync/bass_rms/multiplier", 5.0)
```

---

## Troubleshooting

### OSC messages not received
- Check port 7000 is not blocked
- Verify filter pattern `/td/gen/*` is correct
- Use Monitor CHOP to inspect incoming OSC

### Geometry not switching
- Verify `geo_container` exists and has correct geometry operators
- Check operator names match exactly
- Print debug messages in CHOP Execute

### Colors not updating
- Verify Constant TOPs exist
- Check hex color parsing (needs `#` prefix)
- Test with simple colors first (#FF0000, #00FF00, #0000FF)

### Effects not triggering
- Verify effect operators exist
- Check `run()` delay frames (60 fps = 1 second @ 60 frames)
- Test with simpler effects first

### Sync not working
- Verify audio OSC input is working
- Check sync_map table is populating
- Ensure Timer CHOP is calling `apply_sync_mappings()`

---

## Success Criteria

✅ All OSC messages received and parsed  
✅ Geometry switches in real-time  
✅ Colors update from palette commands  
✅ Effects trigger with correct duration  
✅ Audio features map to visual parameters  
✅ AV Composer demo runs without errors  

---

## Next Phase: Audio Analysis Integration

After generative OSC is working, proceed to **Phase 2 Todo 3**:
- Connect librosa audio analysis from TouchDesigner DJ Suite
- Stream real-time audio features
- Apply sync mappings to live audio

See [NEXT_STEPS.md](NEXT_STEPS.md) for full roadmap.
