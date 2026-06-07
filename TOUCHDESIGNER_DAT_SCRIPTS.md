# TouchDesigner DAT Scripts for OSC Integration

This document contains all Python scripts that need to be created in TouchDesigner DAT operators to implement the generative OSC control system.

## Setup Overview

1. Create `osc_generative` OSC In CHOP (port 7000, filter `/td/gen/*`)
2. Create 6 CHOP Execute DATs (copy the scripts below)
3. Connect DATs to appropriate CHOPs and operators

---

## 1. Geometry Switcher DAT Script

**Name:** `geometry_switcher_exec`
**Type:** CHOP Execute DAT
**Connected to:** `osc_generative` CHOP (via "CHOPs" parameter)

```python
# geometry_switcher_exec - CHOP Execute DAT
# Switches between geometry types (particles, sphere, fractals, mesh)

def onValueChange(channel, sampleIndex, val, prev):
	"""Called when any OSC channel value changes."""
	
	# Only respond to geometry type changes
	if not channel.endswith('/td/gen/geometry/type'):
		return
	
	# Get geometry type from channel name
	# OSC sends string as channel, value is 1.0 when active
	geo_type = channel.split('/')[-1]
	
	# Map geometry types to switch indices
	geo_map = {
		'particles': 0,
		'sphere': 1,
		'fractals': 2,
		'mesh': 3
	}
	
	# Get the switch operator (adjust path to your switch)
	switch = op('/project1/geometry_switch')
	
	if geo_type in geo_map:
		switch.par.index = geo_map[geo_type]
		print(f"Switched geometry to: {geo_type} (index {geo_map[geo_type]})")
	else:
		print(f"Unknown geometry type: {geo_type}")


def whileOn(channel, sampleIndex, val, prev):
	return


def whileOff(channel, sampleIndex, val, prev):
	return


def onOffToOn(channel, sampleIndex, val, prev):
	return


def onOnToOff(channel, sampleIndex, val, prev):
	return
```

---

## 2. Shader Palette DAT Script

**Name:** `shader_palette_exec`
**Type:** CHOP Execute DAT
**Connected to:** `osc_generative` CHOP

```python
# shader_palette_exec - CHOP Execute DAT
# Parses hex colors and updates shader palette constants

def hex_to_rgb(hex_color):
	"""Convert hex color string to RGB tuple (0-1 range)."""
	
	# Remove # if present
	hex_color = hex_color.lstrip('#')
	
	# Parse hex values
	r = int(hex_color[0:2], 16) / 255.0
	g = int(hex_color[2:4], 16) / 255.0
	b = int(hex_color[4:6], 16) / 255.0
	
	return (r, g, b)


def onValueChange(channel, sampleIndex, val, prev):
	"""Called when OSC value changes."""
	
	channel_name = channel.name
	
	# Handle color0
	if 'color0' in channel_name:
		# OSC text comes as channel path, we need to get the actual string
		# For now, hardcode test values (will be improved with Table parsing)
		r, g, b = hex_to_rgb("#FF0000")  # Default red
		
		# Update color0 constant TOP (adjust path)
		color0_top = op('/project1/color0_constant')
		if color0_top:
			color0_top.par.colorr = r
			color0_top.par.colorg = g
			color0_top.par.colorb = b
			print(f"Updated color0: RGB({r:.2f}, {g:.2f}, {b:.2f})")
	
	# Handle color1
	elif 'color1' in channel_name:
		r, g, b = hex_to_rgb("#000000")  # Default black
		
		color1_top = op('/project1/color1_constant')
		if color1_top:
			color1_top.par.colorr = r
			color1_top.par.colorg = g
			color1_top.par.colorb = b
			print(f"Updated color1: RGB({r:.2f}, {g:.2f}, {b:.2f})")
	
	# Handle intensity
	elif 'intensity' in channel_name:
		intensity_chop = op('/project1/intensity_chop')
		if intensity_chop:
			intensity_chop.par.value0 = val
			print(f"Updated intensity: {val:.2f}")


def whileOn(channel, sampleIndex, val, prev):
	return


def whileOff(channel, sampleIndex, val, prev):
	return


def onOffToOn(channel, sampleIndex, val, prev):
	return


def onOnToOff(channel, sampleIndex, val, prev):
	return
```

**Note:** For production, you'll want to improve color parsing to read the actual hex string from OSC. Consider using a Table DAT to store incoming hex values.

---

## 3. Background Color DAT Script

**Name:** `background_color_exec`
**Type:** CHOP Execute DAT
**Connected to:** `osc_generative` CHOP

```python
# background_color_exec - CHOP Execute DAT
# Updates background color from hex OSC messages

def hex_to_rgb(hex_color):
	"""Convert hex color string to RGB tuple (0-1 range)."""
	hex_color = hex_color.lstrip('#')
	r = int(hex_color[0:2], 16) / 255.0
	g = int(hex_color[2:4], 16) / 255.0
	b = int(hex_color[4:6], 16) / 255.0
	return (r, g, b)


def onValueChange(channel, sampleIndex, val, prev):
	"""Called when background color OSC message received."""
	
	if 'background/color' not in channel.name:
		return
	
	# Parse hex color (hardcoded for now, improve with Table lookup)
	r, g, b = hex_to_rgb("#000000")
	
	# Update background constant TOP (adjust path)
	bg_top = op('/project1/background_constant')
	if bg_top:
		bg_top.par.colorr = r
		bg_top.par.colorg = g
		bg_top.par.colorb = b
		print(f"Updated background: RGB({r:.2f}, {g:.2f}, {b:.2f})")


def whileOn(channel, sampleIndex, val, prev):
	return


def whileOff(channel, sampleIndex, val, prev):
	return


def onOffToOn(channel, sampleIndex, val, prev):
	return


def onOnToOff(channel, sampleIndex, val, prev):
	return
```

---

## 4. Effect Trigger DAT Script

**Name:** `effect_trigger_exec`
**Type:** CHOP Execute DAT
**Connected to:** `osc_generative` CHOP

```python
# effect_trigger_exec - CHOP Execute DAT
# Triggers timed visual effects (particle_burst, flash, pulse)

def onValueChange(channel, sampleIndex, val, prev):
	"""Called when effect trigger OSC received."""
	
	channel_name = channel.name
	
	# Particle burst
	if 'particle_burst/trigger' in channel_name and val > 0:
		duration = op('osc_generative')['td/gen/effect/particle_burst/duration']
		intensity = op('osc_generative')['td/gen/effect/particle_burst/intensity']
		
		# Get particle system (adjust path)
		particles = op('/project1/particle_gpu')
		if particles:
			# Boost spawn rate temporarily
			original_rate = particles.par.birth
			particles.par.birth = original_rate * intensity.eval()
			
			# Schedule reset
			def reset_particles():
				particles.par.birth = original_rate
			
			run("reset_particles()", delayFrames=int(duration.eval() * 60))  # 60 FPS
			print(f"Particle burst triggered: {duration.eval()}s @ {intensity.eval()}")
	
	# Flash effect
	elif 'flash/trigger' in channel_name and val > 0:
		duration = op('osc_generative')['td/gen/effect/flash/duration']
		
		# Get flash level (adjust path)
		flash_level = op('/project1/flash_level')
		if flash_level:
			flash_level.par.value0 = 1.0
			
			# Schedule fade out
			def fade_flash():
				flash_level.par.value0 = 0.0
			
			run("fade_flash()", delayFrames=int(duration.eval() * 60))
			print(f"Flash triggered: {duration.eval()}s")
	
	# Pulse effect
	elif 'pulse/trigger' in channel_name and val > 0:
		duration = op('osc_generative')['td/gen/effect/pulse/duration']
		
		# Animate pulse via script (adjust to your setup)
		print(f"Pulse triggered: {duration.eval()}s")


def whileOn(channel, sampleIndex, val, prev):
	return


def whileOff(channel, sampleIndex, val, prev):
	return


def onOffToOn(channel, sampleIndex, val, prev):
	return


def onOnToOff(channel, sampleIndex, val, prev):
	return
```

---

## 5. Sync Mapping DAT Script

**Name:** `sync_mapping_exec`
**Type:** CHOP Execute DAT
**Connected to:** `osc_generative` CHOP

```python
# sync_mapping_exec - CHOP Execute DAT
# Updates sync mapping table (audio feature → visual parameter)

def onValueChange(channel, sampleIndex, val, prev):
	"""Called when sync mapping OSC received."""
	
	channel_name = channel.name
	
	# Check if this is a sync mapping message
	if '/td/gen/sync/' not in channel_name:
		return
	
	# Parse path: /td/gen/sync/{audio_feature}/{property}
	parts = channel_name.split('/')
	if len(parts) < 6:
		return
	
	audio_feature = parts[4]  # bass_rms, onset_strength, etc.
	property_name = parts[5]  # target, curve, multiplier
	
	# Get or create mapping table
	mapping_table = op('/project1/sync_mappings')
	if not mapping_table:
		print("ERROR: sync_mappings table not found!")
		return
	
	# Find or create row for this audio feature
	row_index = None
	for i in range(mapping_table.numRows):
		if mapping_table[i, 0].val == audio_feature:
			row_index = i
			break
	
	if row_index is None:
		# Create new row
		mapping_table.appendRow([audio_feature, '', 'linear', 1.0])
		row_index = mapping_table.numRows - 1
	
	# Update appropriate column
	if property_name == 'target':
		mapping_table[row_index, 1] = channel_name.split('/')[-1]  # Get string value
		print(f"Mapped {audio_feature} → target")
	elif property_name == 'curve':
		mapping_table[row_index, 2] = channel_name.split('/')[-1]
		print(f"Mapped {audio_feature} → curve")
	elif property_name == 'multiplier':
		mapping_table[row_index, 3] = val
		print(f"Mapped {audio_feature} → multiplier = {val}")


def whileOn(channel, sampleIndex, val, prev):
	return


def whileOff(channel, sampleIndex, val, prev):
	return


def onOffToOn(channel, sampleIndex, val, prev):
	return


def onOnToOff(channel, sampleIndex, val, prev):
	return
```

**Required Table DAT:**
- Name: `sync_mappings`
- Columns: `audio_feature`, `visual_param`, `curve_type`, `multiplier`
- Initial rows: Empty (populated via OSC)

---

## 6. Parameter Control DAT Script

**Name:** `param_control_exec`
**Type:** CHOP Execute DAT
**Connected to:** `osc_generative` CHOP

```python
# param_control_exec - CHOP Execute DAT
# Arbitrary parameter control via OSC (/td/gen/param/{operator}/{parameter})

def onValueChange(channel, sampleIndex, val, prev):
	"""Called when parameter control OSC received."""
	
	channel_name = channel.name
	
	# Check if this is a parameter control message
	if '/td/gen/param/' not in channel_name:
		return
	
	# Parse path: /td/gen/param/{operator_name}/{parameter_name}
	parts = channel_name.split('/')
	if len(parts) < 6:
		return
	
	operator_name = parts[4]  # noise1, rotate1, blur1, etc.
	param_name = parts[5]     # amplitude, speed, size, etc.
	
	# Find operator (search in project)
	target_op = op(f'/project1/{operator_name}')
	if not target_op:
		print(f"ERROR: Operator not found: {operator_name}")
		return
	
	# Update parameter
	if hasattr(target_op.par, param_name):
		setattr(target_op.par, param_name, val)
		print(f"Updated {operator_name}.{param_name} = {val}")
	else:
		print(f"ERROR: Parameter not found: {operator_name}.{param_name}")


def whileOn(channel, sampleIndex, val, prev):
	return


def whileOff(channel, sampleIndex, val, prev):
	return


def onOffToOn(channel, sampleIndex, val, prev):
	return


def onOnToOff(channel, sampleIndex, val, prev):
	return
```

---

## Manual Setup Steps in TouchDesigner

### Step 1: Create OSC In CHOP

1. Create new **OSC In CHOP** (press Tab → type "oscin")
2. Name it: `osc_generative`
3. Set parameters:
   - Port: `7000`
   - Inputs Filter: `/td/gen/*`
   - Auto Create CHOPs: ON (checkbox)

### Step 2: Create DAT Operators

For each of the 6 scripts above:

1. Create **CHOP Execute DAT** (Tab → "chopexec")
2. Name it according to script name
3. Copy the Python code into the DAT
4. In DAT parameters:
   - CHOPs: Point to `osc_generative`
   - Active: ON (checkbox)

### Step 3: Create Required Operators

The scripts reference these operators (create or rename existing):

**For Geometry Switcher:**
- `geometry_switch` - Switch TOP with 4 inputs (particles, sphere, fractals, mesh)

**For Shader Palette:**
- `color0_constant` - Constant TOP (shader primary color)
- `color1_constant` - Constant TOP (shader secondary color)
- `intensity_chop` - Constant CHOP (shader intensity value)

**For Background:**
- `background_constant` - Constant TOP (background color layer)

**For Effects:**
- `particle_gpu` - Particle GPU TOP (with `birth` parameter)
- `flash_level` - Constant CHOP (flash intensity 0-1)

**For Sync Mappings:**
- `sync_mappings` - Table DAT (4 columns: audio_feature, visual_param, curve_type, multiplier)

### Step 4: Wire Everything Up

1. OSC In CHOP → All 6 CHOP Execute DATs (via "CHOPs" parameter)
2. Geometry Switch inputs → 4 geometry generators
3. Color constants → Shader/material inputs
4. Flash level → Over TOP or multiply
5. Sync mappings table → Audio analysis pipeline (future)

---

## Testing

Run the test script:

```bash
cd /Users/thomasadair/projects/touchdesigner-dj-suite
python test_td_osc_integration.py
```

Watch TouchDesigner for:
- Geometry switching between particles/sphere/fractals/mesh
- Color changes (red/black → blue/cyan → purple/pink)
- Flash effects
- Particle bursts
- Console messages from DAT scripts

---

## Troubleshooting

**No OSC received:**
- Check port 7000 is not blocked
- Verify filter `/td/gen/*` in OSC In CHOP
- Check `osc_generative` CHOP has channels

**DATs not executing:**
- Verify "Active" checkbox is ON
- Check "CHOPs" parameter points to `osc_generative`
- Look for Python errors in textport (Alt+T)

**Operators not found:**
- Check operator paths in scripts match your network
- Use relative paths (.../operator_name) if needed
- Verify operator names are exact (case-sensitive)

**Colors not parsing:**
- Current scripts have hardcoded hex values
- Improve by storing hex strings in Table DAT
- Parse table in onValueChange to get real OSC color data

---

## Next Steps After Implementation

1. **Test with AV Composer:** Connect orchestrator to send real OSC
2. **Audio Analysis Integration:** Connect audio features to sync mappings
3. **Dynamic Geometry:** Create more geometry types (ribbon, tunnel, etc.)
4. **Advanced Effects:** Add more timed effects (glow, distortion, kaleidoscope)
5. **Bidirectional Communication:** Send TouchDesigner state back to orchestrator

