# TouchDesigner Body Aura Build Guide — TD-DJ-Suite Fire Effect

Node-by-node build guide for the fiery body aura effect. Thomas is the focal point — the aura wraps around his body silhouette, not the whole scene.

**Goal:** Body segmentation mask → edge detect → fire particles + GLSL flame shader → bloom → composite over live camera.

---

## Architecture Overview

```
                        ┌───────────────────┐
   movement_tracker.py  │  Python (external) │
   (MediaPipe + OSC)    │  writes mmap mask  │
                        │  sends OSC /move/* │
                        └────┬──────────┬────┘
                             │          │
                      mmap file      OSC port 7000
                             │          │
                ┌────────────▼──┐  ┌────▼───────────┐
                │ body_mask_top │  │  osc_body       │
                │ (Script TOP)  │  │  (OSC In CHOP)  │
                └──────┬────────┘  └────┬────────────┘
                       │                │
                ┌──────▼────────┐  ┌────▼────────────────┐
                │  edge_detect  │  │  osc_body_receiver   │
                │  (Edge TOP)   │  │  (CHOP Execute DAT)  │
                └──┬─────────┬──┘  └────┬────────────────┘
                   │         │          │
        ┌──────────▼──┐  ┌──▼──────────▼─────────────┐
        │ particle_gpu│  │  body_channels             │
        │ (Particle   │  │  (Constant CHOP)           │
        │  GPU TOP)   │  └──────────┬─────────────────┘
        └──────┬──────┘             │
               │              ┌─────▼──────────────────┐
               │              │  audio_in → spectrum    │
               │              │  → audio_reactive_mapper│
               │              │  → audio_params (CHOP)  │
               │              └─────┬──────────────────┘
               │                    │
        ┌──────▼────────────────────▼──┐
        │       fire_aura_glsl         │
        │       (GLSL TOP)             │
        │  inputs: edge + particles    │
        │  uniforms: audio + motion    │
        └──────────┬───────────────────┘
                   │
            ┌──────▼──────┐
            │  bloom_post  │
            │  (Bloom TOP) │
            └──────┬──────┘
                   │
            ┌──────▼──────────────┐
            │  final_composite    │
            │  (Composite TOP)    │
            │  camera_in UNDER    │
            │  aura layer OVER    │
            └─────────────────────┘
```

---

## Prerequisites

- TouchDesigner 2023.x or later (free Non-Commercial or Pro)
- Python 3.11 with `mediapipe`, `opencv-python`, `python-osc` installed
- `movement_tracker.py` running externally (or `body_mask_sender.py`)
- Webcam / Insta360 Link connected
- DJ audio routed into your system (Loopback or audio interface)

---

## Session 2: Body Mask → Fire Aura Visual Pipeline

### Step 1: Body Segmentation Mask Input

**Create Script TOP — `body_mask_top`**

| Parameter | Value |
|-----------|-------|
| Type | Script TOP |
| Name | `body_mask_top` |
| Resolution | 640 x 480 |
| Pixel Format | 8-bit fixed (Mono) |
| Callbacks DAT | `segmentation_mask_reader` |
| Cook Every Frame | ON |

Create a Text DAT named `segmentation_mask_reader` and paste the contents of `touchdesigner/scripts/segmentation_mask_reader.py`.

This reads `/tmp/djsam_bodymask.raw` via mmap every frame and outputs a grayscale body mask texture.

**Verify:** Start `movement_tracker.py` externally, then check that `body_mask_top` shows a white silhouette on black background.

---

### Step 2: Edge Detection

**Create Edge TOP — `edge_detect`**

| Parameter | Value |
|-----------|-------|
| Type | Edge TOP |
| Name | `edge_detect` |
| Input | `body_mask_top` |
| Compute Type | Sobel |
| Threshold | 0.1 |
| Output | Mono |

**Then add a Blur TOP — `edge_blur`**

| Parameter | Value |
|-----------|-------|
| Type | Blur TOP |
| Name | `edge_blur` |
| Input | `edge_detect` |
| Size | 4.0 (pixels) |
| Filter | Gaussian |

This produces a soft body edge mask — the emission zone for fire particles and the input mask for the GLSL flame shader.

---

### Step 3: Particle GPU System

**Create Particle GPU TOP — `particle_gpu`**

| Parameter | Value |
|-----------|-------|
| Type | Particle GPU TOP |
| Name | `particle_gpu` |
| Resolution | 1280 x 720 |
| Birth Rate | 500 (default, driven by script) |
| Life | 1.2 sec |
| Life Variance | 0.4 |
| Speed | 1.5 |
| Speed Variance | 0.3 |
| Gravity Y | 0.5 (fire rises) |
| Particle Size | 0.5 |
| Birth Shape | Point (driven by emitter_points Script CHOP) |
| Birth SOP | (see below) |

**Particle Emission Points:**

Create a Script CHOP named `emitter_points` with callbacks DAT pointing to `particle_emitter_controller.py`. This extracts body contour points from the mask and outputs tx/ty/tz + normals.

To connect emission points to the particle system:
1. Create a CHOP to SOP — name: `emit_chop_to_sop`
   - Input: `emitter_points`
   - This converts the point channels to a SOP point cloud
2. Set `particle_gpu` → Birth → Source SOP → `emit_chop_to_sop`

**Particle Color:**

Set particle color ramp (Birth Color → Death Color):
- Birth: `#FF6600` (bright orange)
- Mid:   `#FF2200` (red-orange)
- Death: `#330000` (dark ember, alpha → 0)

Enable "Use Alpha" and set Death Alpha to 0.

---

### Step 4: Fire GLSL Shader

**Create GLSL TOP — `fire_aura_glsl`**

| Parameter | Value |
|-----------|-------|
| Type | GLSL TOP |
| Name | `fire_aura_glsl` |
| Resolution | 1280 x 720 |
| Pixel Format | 16-bit float (RGBA) |
| Output Alpha | ON |

**Pixel Shader:**
Create a Text DAT named `fire_aura_shader_code` and paste the contents of `touchdesigner/shaders/fire_aura.glsl`.

Set the GLSL TOP's "Pixel Shader" DAT to `fire_aura_shader_code`.

**Inputs (wire these TOPs into GLSL TOP inputs):**

| Input Index | Source | Description |
|-------------|--------|-------------|
| 0 | `edge_blur` | Body edge mask |
| 1 | `motion_energy_top` | CHOP to TOP from motion energy |
| 2 | `audio_energy_top` | CHOP to TOP from bass energy |

For inputs 1 and 2, create CHOP to TOP operators:
- `motion_energy_top`: CHOP to TOP, input = body_channels (motion_energy channel)
- `audio_energy_top`: CHOP to TOP, input = audio_params (bass_smooth channel)

**Custom Uniforms:**

On the GLSL TOP's "Vectors 1" page, add float parameters:
- value1 = uFlameIntensity (default 0.5)
- value2 = uTurbulence (default 0.3)
- value3 = uDistortion (default 0.2)
- value4 = uSparkle (default 0.0)
- value5 = uMotionEnergy (default 0.0)
- value6 = uBassEnergy (default 0.0)
- value7 = uMidEnergy (default 0.0)
- value8 = uHighEnergy (default 0.0)
- value9 = uBurstDecay (default 0.0)

These are driven automatically by `aura_compositor.py`.

---

### Step 5: Combine Particles + GLSL Flame

**Create Composite TOP — `flame_layers`**

| Parameter | Value |
|-----------|-------|
| Type | Composite TOP |
| Name | `flame_layers` |
| Input 0 | `fire_aura_glsl` |
| Input 1 | `particle_gpu` |
| Operation | Add |

This adds the particle fire on top of the GLSL procedural flame.

---

### Step 6: Bloom Post-Processing

**Create Bloom TOP — `bloom_post`**

| Parameter | Value |
|-----------|-------|
| Type | Bloom TOP |
| Name | `bloom_post` |
| Input | `flame_layers` |
| Size | 0.4 |
| Intensity | 0.6 |
| Threshold | 0.3 |

This adds the hot glow around flames. Size and intensity are driven by audio (highs → sparkle/bloom).

---

### Step 7: Burst Flash Overlay

**Create Constant TOP — `burst_flash`**

| Parameter | Value |
|-----------|-------|
| Type | Constant TOP |
| Name | `burst_flash` |
| Resolution | 1280 x 720 |
| Color R | 1.0 |
| Color G | 0.95 |
| Color B | 0.8 |
| Color A | 0.0 (driven by script on onset) |

This flashes warm white on bass onsets. Alpha is driven by `aura_compositor.py`.

---

### Step 8: Final Composite Over Camera

**Create Video Device In TOP — `camera_in`**

| Parameter | Value |
|-----------|-------|
| Type | Video Device In TOP |
| Name | `camera_in` |
| Device | Your webcam / Insta360 Link |
| Resolution | 1280 x 720 |

**Create Composite TOP — `final_composite`**

| Parameter | Value |
|-----------|-------|
| Type | Composite TOP |
| Name | `final_composite` |
| Input 0 | `camera_in` (background) |
| Input 1 | `bloom_post` (fire aura) |
| Input 2 | `burst_flash` (onset flash) |
| Operation | Over (pre-multiplied alpha) |

The fire aura composites OVER the camera feed. Thomas is the focal point — the aura hugs his body silhouette.

**Output to screen:**
- Wire `final_composite` → Window COMP (or Container COMP) for fullscreen output
- Or wire to NDI Out TOP / Syphon Out TOP for OBS capture

---

### Step 9: Pipeline Controller

**Create Execute DAT — `aura_compositor`**

Paste `touchdesigner/scripts/aura_compositor.py` into a Text DAT, then reference it from an Execute DAT.

| Parameter | Value |
|-----------|-------|
| Execute on Frame Start | ON |
| Active | ON |

This script runs every frame, reads `audio_params` and `body_channels`, and pushes values into the particle system, GLSL shader, bloom, and composite.

---

## Session 3: Audio Analysis → Parameter Mapping

### Step 1: Audio Input

**Create Audio Device In CHOP — `audio_in`**

| Parameter | Value |
|-----------|-------|
| Type | Audio Device In CHOP |
| Name | `audio_in` |
| Driver | CoreAudio (macOS) |
| Device | Your DJ audio output / Loopback |
| Sample Rate | 44100 |
| Channels | 2 (stereo) |

**Tip:** If using Serato/Rekordbox, route the master output through Loopback or BlackHole so TD can capture it.

---

### Step 2: Audio Spectrum Analysis

**Create Audio Spectrum CHOP — `audio_spectrum`**

| Parameter | Value |
|-----------|-------|
| Type | Audio Spectrum CHOP |
| Name | `audio_spectrum` |
| Input | `audio_in` |
| Output | Magnitude |
| FFT Size | 2048 |
| Window | Hanning |

This gives you ~1024 frequency bins. At 44100 Hz sample rate, each bin ≈ 21.5 Hz.

---

### Step 3: Audio Parameter Storage

**Create Constant CHOP — `audio_params`**

Create the following channels (all default to 0):

```
bass_energy    bass_smooth
mid_energy     mid_smooth
high_energy    high_smooth
onset          onset_trigger
flame_intensity    particle_size    emission_rate
turbulence    velocity    distortion
sparkle    bloom_intensity
burst_active    burst_decay
```

---

### Step 4: Audio Reactive Mapper

**Create CHOP Execute DAT — `audio_reactive_mapper`**

Paste the contents of `touchdesigner/scripts/audio_reactive_mapper.py`.

| Parameter | Value |
|-----------|-------|
| CHOPs | `audio_spectrum` |
| Active | ON |
| Value Change | ON |

---

### Step 5: Frequency Band → Visual Parameter Mapping

Here is the complete mapping driven by `audio_reactive_mapper.py`:

#### Bass (20–200 Hz) → Fire Body

| Audio Input | Visual Parameter | Range | Multiplier | Effect |
|------------|-----------------|-------|------------|--------|
| Bass energy | `flame_intensity` | 0–3.0 | 3.0× | Flame brightness + size |
| Bass energy | `particle_size` | 0.3–3.0 | 2.5× | Larger fire particles |
| Bass energy | `emission_rate` | 100–5000 | 5.0× | More particles spawned |

On heavy bass drops, the aura flares up — bigger, brighter, more particles.

#### Mids (200 Hz–2 kHz) → Movement + Turbulence

| Audio Input | Visual Parameter | Range | Multiplier | Effect |
|------------|-----------------|-------|------------|--------|
| Mid energy | `turbulence` | 0–2.0 | 2.0× | Flame noise turbulence |
| Mid energy | `velocity` | 0.5–3.5 | 3.0× | Particle speed |
| Mid energy | `distortion` | 0–1.5 | 1.5× | Heat distortion warp |

Mids drive the motion of the flames — more melodic content = more fluid movement.

#### Highs (2 kHz–20 kHz) → Sparkle + Glow

| Audio Input | Visual Parameter | Range | Multiplier | Effect |
|------------|-----------------|-------|------------|--------|
| High energy | `sparkle` | 0–4.0 | 4.0× | Bright glint particles |
| High energy | `bloom_intensity` | 0.2–2.0 | 2.0× | Post-process glow size |

Hi-hats and cymbals create sparkle points and expanded bloom.

#### Onset Detection → Burst Triggers

| Condition | Visual Effect | Duration |
|-----------|--------------|----------|
| Bass transient > 0.15 | Particle burst (5000 extra particles) | ~120ms cooldown |
| Bass transient > 0.15 | White-hot flash overlay (warm white) | Exponential decay (0.92/frame) |
| Bass transient > 0.15 | Aura expansion (+8% radius) | Decay with burst_decay |

**Onset detection parameters** (tunable in `audio_reactive_mapper.py`):
- `ONSET_THRESHOLD = 0.15` — Minimum bass energy jump to trigger
- `ONSET_COOLDOWN_MS = 120` — Prevent double-triggers
- `ONSET_DECAY_RATE = 0.92` — Visual decay speed

---

### Step 6: OSC Body Data Input

**Create OSC In CHOP — `osc_body`**

| Parameter | Value |
|-----------|-------|
| Type | OSC In CHOP |
| Name | `osc_body` |
| Port | 7000 |
| Inputs Filter | `/movement/*` |

**Create Constant CHOP — `body_channels`**

Channels:
```
lh_x  lh_y  rh_x  rh_y
lh_height  rh_height
hand_spread  body_height  head_x  head_y  shoulder_tilt
motion_energy  tracking_active  mask_active  num_people
```

**Create CHOP Execute DAT — `osc_body_receiver`**

Paste `touchdesigner/scripts/osc_body_receiver.py`.

| Parameter | Value |
|-----------|-------|
| CHOPs | `osc_body` |
| Active | ON |

---

## Complete Operator List

### TOPs (Textures)

| Name | Type | Notes |
|------|------|-------|
| `body_mask_top` | Script TOP | Reads mmap segmentation mask |
| `edge_detect` | Edge TOP | Sobel edge from body mask |
| `edge_blur` | Blur TOP | Softens edge for flame zone |
| `particle_gpu` | Particle GPU TOP | Fire particles along body contour |
| `fire_aura_glsl` | GLSL TOP | Procedural flame shader |
| `flame_layers` | Composite TOP | Particles + GLSL flame (Add) |
| `bloom_post` | Bloom TOP | Glow post-processing |
| `burst_flash` | Constant TOP | Onset flash overlay |
| `camera_in` | Video Device In TOP | Live camera feed |
| `motion_energy_top` | CHOP to TOP | Motion data as texture |
| `audio_energy_top` | CHOP to TOP | Audio data as texture |
| `final_composite` | Composite TOP | Camera + aura (Over) |

### CHOPs (Channels)

| Name | Type | Notes |
|------|------|-------|
| `osc_body` | OSC In CHOP | Port 7000, filter `/movement/*` |
| `body_channels` | Constant CHOP | Body tracking data |
| `audio_in` | Audio Device In CHOP | DJ audio input |
| `audio_spectrum` | Audio Spectrum CHOP | FFT analysis |
| `audio_params` | Constant CHOP | Mapped audio parameters |
| `emitter_points` | Script CHOP | Contour emission points |

### DATs (Scripts)

| Name | Type | Script File |
|------|------|-------------|
| `segmentation_mask_reader` | Text DAT | `touchdesigner/scripts/segmentation_mask_reader.py` |
| `osc_body_receiver` | CHOP Execute DAT | `touchdesigner/scripts/osc_body_receiver.py` |
| `audio_reactive_mapper` | CHOP Execute DAT | `touchdesigner/scripts/audio_reactive_mapper.py` |
| `particle_emitter_controller` | Text DAT (Script CHOP callback) | `touchdesigner/scripts/particle_emitter_controller.py` |
| `aura_compositor` | Execute DAT | `touchdesigner/scripts/aura_compositor.py` |
| `fire_aura_shader_code` | Text DAT | `touchdesigner/shaders/fire_aura.glsl` |

---

## Quick Start Checklist

1. [ ] Open `dj_visuals.8.toe` in TouchDesigner
2. [ ] Create all TOPs, CHOPs, and DATs listed above
3. [ ] Paste scripts from `touchdesigner/scripts/` into corresponding DATs
4. [ ] Paste `fire_aura.glsl` into `fire_aura_shader_code` Text DAT
5. [ ] Wire everything per the architecture diagram
6. [ ] Start `movement_tracker.py` externally: `python python/movement_tracker.py --max-people 1`
7. [ ] Route DJ audio into system (Loopback / BlackHole)
8. [ ] Set `audio_in` device to your audio source
9. [ ] Check `body_mask_top` shows your silhouette
10. [ ] Check `edge_detect` shows body outline
11. [ ] Check `particle_gpu` spawns particles along body edge
12. [ ] Check `fire_aura_glsl` renders flame effect
13. [ ] Check `final_composite` shows camera + fire aura overlay
14. [ ] Play music — watch flames react to bass, mids, highs
15. [ ] Dance — watch aura expand with movement

---

## Tuning Tips

**Flame too subtle:** Increase `FLAME_INTENSITY_MULT` in `audio_reactive_mapper.py` or boost `value1` on the GLSL TOP.

**Flame too aggressive:** Lower the multipliers in `audio_reactive_mapper.py` or increase `BASS_SMOOTH` / `MID_SMOOTH` values.

**Mask edges are jittery:** Increase the Gaussian blur kernel in `movement_tracker.py` (line with `GaussianBlur`). Or increase `edge_blur` size in TD.

**Particles not following body:** Check that `emitter_points` Script CHOP is cooking (has output channels). Verify `body_mask_top` is receiving mask data.

**Onset triggers too often:** Increase `ONSET_THRESHOLD` or `ONSET_COOLDOWN_MS` in `audio_reactive_mapper.py`.

**Color palette:** Edit the `fireColor()` function in `fire_aura.glsl` to change the gradient stops. The palette is defined as c0–c5 (ember → white-hot).

**Performance:** If frame rate drops below 30 FPS:
- Reduce `body_mask_top` resolution to 320x240 (update MASK_W/MASK_H in both tracker and reader)
- Reduce `MAX_EMIT_POINTS` in `particle_emitter_controller.py`
- Lower `particle_gpu` birth rate
- Run `movement_tracker.py` with `--camera 0` and lower resolution
