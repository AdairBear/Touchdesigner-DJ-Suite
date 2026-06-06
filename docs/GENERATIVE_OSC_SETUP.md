# TouchDesigner Generative OSC Integration Guide

## Overview

This guide explains how to add AI-driven generative visual control to your TouchDesigner project, extending the existing movement/audio sensor system with high-level creative commands from the AV Composer.

## OSC Address Structure

### Existing Sensor Data (Preserved)
- `/td/sensor/movement/p{0-3}/*` - Movement tracking per person
- `/td/sensor/audio/*` - Audio analysis features

### New Generative Commands (Phase 2)
- `/td/gen/geometry/*` - Geometry configuration
- `/td/gen/shader/*` - Shader and color control
- `/td/gen/background/*` - Background settings
- `/td/gen/effect/*` - Effect triggers
- `/td/gen/sync/*` - Audio-visual sync mappings
- `/td/gen/param/*` - Arbitrary parameter control

---

## Implementation Steps

### Step 1: Add Generative OSC In CHOP

1. In your TouchDesigner network, add a new **OSC In CHOP**
2. Name it: `osc_generative`
3. Configure:
   - **Network Address**: `127.0.0.1`
   - **Port**: `7000` (same as sensor OSC)
   - **Protocol**: UDP
   - **Filter**: `/td/gen/*` (to route generative commands separately)

### Step 2: Create Geometry Switcher

The geometry type command determines the primary visual form.

1. Add a **Select CHOP** to extract geometry type:
   ```
   Select Pattern: /td/gen/geometry/type
   ```

2. Add a **CHOP Execute DAT** to the Select CHOP
3. In the CHOP Execute DAT, add:
   ```python
   def onValueChange(channel, sampleIndex, val, prev):
       """Switch geometry based on OSC command."""
       geometry_type = channel.name.split('/')[-1]
       
       # Get container with geometry TOPs
       geo_container = op('geo_container')
       
       # Map geometry types to operators
       geometry_map = {
           'particles': 'particle_top',
           'sphere': 'sphere_sop',
           'fractals': 'fractal_top',
           'mesh': 'mesh_sop',
       }
       
       # Switch to requested geometry
       if geometry_type in geometry_map:
           target_op = geometry_map[geometry_type]
           op('geo_switch').par.index = list(geometry_map.keys()).index(geometry_type)
   ```

4. Create a **Switch TOP** named `geo_switch` that outputs to your render pipeline

### Step 3: Shader Palette System

Handle color palette changes for shaders.

1. Add **Select CHOP** for palette colors:
   ```
   Select Pattern: /td/gen/shader/palette/*
   ```

2. Add **CHOP Execute DAT**:
   ```python
   def onValueChange(channel, sampleIndex, val, prev):
       """Update shader color palette."""
       if 'color0' in channel.name:
           # Parse hex color from OSC string (sent as text)
           hex_color = str(val)
           r, g, b = hex_to_rgb(hex_color)
           op('constant_color0').par.colorr = r
           op('constant_color0').par.colorg = g
           op('constant_color0').par.colorb = b
       
       elif 'color1' in channel.name:
           hex_color = str(val)
           r, g, b = hex_to_rgb(hex_color)
           op('constant_color1').par.colorr = r
           op('constant_color1').par.colorg = g
           op('constant_color1').par.colorb = b
       
       elif 'intensity' in channel.name:
           op('shader_intensity').par.value0 = val
   
   def hex_to_rgb(hex_str):
       """Convert hex color to RGB 0-1 range."""
       hex_str = hex_str.lstrip('#')
       r = int(hex_str[0:2], 16) / 255.0
       g = int(hex_str[2:4], 16) / 255.0
       b = int(hex_str[4:6], 16) / 255.0
       return r, g, b
   ```

### Step 4: Effect Trigger System

Handle timed visual effects.

1. Add **Select CHOP** for effect triggers:
   ```
   Select Pattern: /td/gen/effect/*
   ```

2. Add **CHOP Execute DAT**:
   ```python
   def onValueChange(channel, sampleIndex, val, prev):
       """Trigger visual effects."""
       if '/trigger' in channel.name:
           # Extract effect name
           effect_name = channel.name.split('/')[3]  # /td/gen/effect/{name}/trigger
           
           # Get effect parameters
           duration = op('osc_generative')[f'/td/gen/effect/{effect_name}/duration']
           
           if effect_name == 'particle_burst':
               # Trigger particle emission burst
               op('particle_emit').par.birth = 1000  # Burst size
               run(f"op('particle_emit').par.birth = 0", delayFrames=int(duration * 60))
           
           elif effect_name == 'flash':
               # Trigger screen flash
               op('flash_level').par.value0 = 1.0
               run(f"op('flash_level').par.value0 = 0", delayFrames=int(duration * 60))
           
           elif effect_name == 'pulse':
               # Trigger geometry pulse
               op('geo_scale').par.scale = 1.5
               run(f"op('geo_scale').par.scale = 1.0", delayFrames=int(duration * 60))
   ```

### Step 5: Sync Target Mapping

Map audio features to visual parameters dynamically.

1. Add **Table DAT** named `sync_map`:
   - Column 1: `audio_feature`
   - Column 2: `visual_param`
   - Column 3: `curve`
   - Column 4: `multiplier`

2. Add **CHOP Execute DAT** on generative OSC:
   ```python
   def onValueChange(channel, sampleIndex, val, prev):
       """Update sync mapping table."""
       if '/td/gen/sync/' in channel.name:
           parts = channel.name.split('/')
           audio_feature = parts[3]  # /td/gen/sync/{feature}/{param}
           param_name = parts[4]
           
           # Update sync map table
           sync_table = op('sync_map')
           
           # Find or create row for this audio feature
           row = None
           for i in range(1, sync_table.numRows):
               if sync_table[i, 0] == audio_feature:
                   row = i
                   break
           
           if row is None:
               row = sync_table.numRows
               sync_table.appendRow([audio_feature, '', 'linear', 1.0])
           
           # Update parameter
           if param_name == 'target':
               sync_table[row, 1] = str(val)
           elif param_name == 'curve':
               sync_table[row, 2] = str(val)
           elif param_name == 'multiplier':
               sync_table[row, 3] = str(val)
   ```

3. Add **Python SOP/CHOP** to apply mappings:
   ```python
   # In a CHOP Execute or Timer CHOP
   def apply_sync_mappings():
       """Apply audio→visual mappings from sync table."""
       sync_table = op('sync_map')
       audio_osc = op('osc_audio')  # Existing audio OSC input
       
       for i in range(1, sync_table.numRows):
           audio_feature = sync_table[i, 0].val
           visual_param = sync_table[i, 1].val
           curve = sync_table[i, 2].val
           multiplier = float(sync_table[i, 3].val)
           
           # Get audio value
           if audio_feature in audio_osc.chans():
               audio_value = audio_osc[audio_feature].eval()
               
               # Apply mapping curve
               if curve == 'exponential':
                   mapped = audio_value ** 2
               elif curve == 'logarithmic':
                   import math
                   mapped = math.log1p(audio_value * 10) / math.log1p(10)
               else:  # linear
                   mapped = audio_value
               
               # Apply multiplier
               final_value = mapped * multiplier
               
               # Set visual parameter
               if hasattr(op, visual_param):
                   op(visual_param).par.value0 = final_value
   ```

### Step 6: Arbitrary Parameter Control

Allow direct parameter setting.

1. Add **CHOP Execute DAT**:
   ```python
   def onValueChange(channel, sampleIndex, val, prev):
       """Set arbitrary parameters."""
       if '/td/gen/param/' in channel.name:
           # Extract parameter path: /td/gen/param/{path}
           param_path = channel.name.replace('/td/gen/param/', '')
           parts = param_path.split('/')
           
           if len(parts) == 2:
               op_name, param_name = parts
               target_op = op(op_name)
               if target_op and hasattr(target_op.par, param_name):
                   setattr(target_op.par, param_name, val)
   ```

---

## Testing the Integration

### Test 1: Geometry Switching

From Python (or via AV Composer):
```python
from av_composer import TouchDesignerController

td = TouchDesignerController()
td.set_geometry_type("particles")  # Should switch to particle system
```

### Test 2: Color Palette

```python
td.set_shader_palette(["#FF0000", "#0000FF"], intensity=0.9)
```

Check that your shader colors update in real-time.

### Test 3: Effect Trigger

```python
td.trigger_effect("particle_burst", duration=2.0, intensity=0.8)
```

Should see a 2-second particle burst.

### Test 4: Sync Mapping

```python
td.set_sync_target("bass_rms", "particle_spawn_rate", "exponential", 5.0)
```

When bass plays, particle spawn rate should increase exponentially.

---

## Network Architecture Example

```
┌─────────────────────────────────────────────────────────────┐
│                    TouchDesigner Network                     │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  [OSC In: Sensor Data]     [OSC In: Generative Commands]    │
│   port 7000                 port 7000                        │
│   filter: /td/sensor/*      filter: /td/gen/*                │
│          │                           │                       │
│          ├─> Movement Tracker        ├─> Geometry Switch     │
│          │   (existing)              ├─> Shader Palette      │
│          ├─> Audio Analysis          ├─> Effect Triggers     │
│          │   (existing)              ├─> Sync Map Table      │
│          │                           └─> Param Control       │
│          │                                   │               │
│          ▼                                   ▼               │
│    [Reactive Visuals]  ◄──────┬──────►  [Generative]        │
│      (sensor-driven)           │         (AI-driven)         │
│                                │                             │
│                          [Render Pipeline]                   │
│                                │                             │
│                                ▼                             │
│                           [Output]                           │
│                      (OBS/Spout/NDI)                         │
└─────────────────────────────────────────────────────────────┘
```

---

## Best Practices

1. **Keep Sensor and Generative Separate**
   - Use different prefixes (`/td/sensor` vs `/td/gen`)
   - Allows hybrid mode: live DJ + AI visuals

2. **Use CHOP Execute for Dynamic Behavior**
   - Geometry switching
   - Effect triggers
   - Parameter routing

3. **Use Tables for Data**
   - Sync mapping table
   - Color palette storage
   - Effect configuration

4. **Test Incrementally**
   - Add one OSC handler at a time
   - Verify each command works before adding next
   - Use Monitor CHOPs to debug OSC messages

5. **Error Handling**
   - Check if operators exist before accessing
   - Validate hex colors before parsing
   - Handle missing parameters gracefully

---

## Next Steps After Implementation

Once the generative OSC system is working:

1. **Test with AV Composer demo**
   ```bash
   cd /Users/thomasadair/projects/av-composer
   python -m av_composer.orchestrator
   ```

2. **Create visual presets** matching music templates:
   - Jungle 170 BPM → red particles, heavy bass pulse
   - Techno 128 BPM → blue fractals, minimal geometry

3. **Build custom effects** triggered by AI:
   - Transition effects between sections
   - Build/drop visual markers
   - Breakdown ambient modes

4. **Fine-tune sync mappings**:
   - Adjust multipliers for visual impact
   - Test different curve types
   - Create responsive but not overwhelming effects
