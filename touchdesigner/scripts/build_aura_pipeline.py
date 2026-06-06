# build_aura_pipeline.py
# ======================
# Run this in TouchDesigner's Textport (Dialogs → Textport and DATs)
# or paste into a Text DAT and run with: exec(op('build_script').text)
#
# Creates the complete fire body aura pipeline inside /project1/
# Operators, connections, parameters — everything.

import os

ROOT = '/project1'

# Helper to get/create operator
def ensure_op(path, optype):
    """Create operator if it doesn't exist."""
    name = path.split('/')[-1]
    parent_path = '/'.join(path.split('/')[:-1])
    parent = op(parent_path)
    existing = op(path)
    if existing is not None:
        return existing
    return parent.create(optype, name)


print("=" * 60)
print("  DJ SAM — Fire Body Aura Pipeline Builder")
print("=" * 60)

# ============================================================
# Delete default demo operators to clean up
# ============================================================
print("\n[1/8] Cleaning up default operators...")
for name in ['moviefilein1', 'displace1', 'geo1', 'chopto1', 'noise1']:
    existing = op(ROOT + '/' + name)
    if existing is not None:
        existing.destroy()
        print(f"  Removed default: {name}")


# ============================================================
# BODY MASK INPUT CHAIN
# ============================================================
print("\n[2/8] Creating body mask input chain...")

# Script TOP for reading mmap segmentation mask
body_mask = ensure_op(ROOT + '/body_mask_top', 'scriptTOP')
body_mask.par.resolutionw = 640
body_mask.par.resolutionh = 480

# Text DAT for the mask reader callback script
mask_reader_dat = ensure_op(ROOT + '/segmentation_mask_reader', 'textDAT')
mask_script_path = project.folder + '/touchdesigner/scripts/segmentation_mask_reader.py'
if os.path.exists(mask_script_path):
    mask_reader_dat.par.file = mask_script_path
    mask_reader_dat.par.loadonstart = True
    mask_reader_dat.par.write = False
    mask_reader_dat.par.syncfile = True
    print(f"  Loaded script from: {mask_script_path}")
else:
    # Inline fallback — minimal mask reader
    mask_reader_dat.text = '''# segmentation_mask_reader.py
# Reads body mask from /tmp/djsam_bodymask.raw via mmap
import numpy as np, mmap, os, struct

MASK_PATH = "/tmp/djsam_bodymask.raw"
MASK_W, MASK_H = 640, 480
HEADER_SIZE = 8
TOTAL_SIZE = HEADER_SIZE + MASK_W * MASK_H
_fh = None
_mm = None
_last_frame = -1

def _open_mmap():
    global _fh, _mm
    if _mm is not None:
        try: _mm.close()
        except: pass
    if _fh is not None:
        try: _fh.close()
        except: pass
    if not os.path.exists(MASK_PATH):
        _fh = _mm = None
        return False
    try:
        _fh = open(MASK_PATH, "r+b")
        _mm = mmap.mmap(_fh.fileno(), TOTAL_SIZE, access=mmap.ACCESS_READ)
        return True
    except:
        _fh = _mm = None
        return False

def cook(scriptOP):
    global _mm, _last_frame
    if _mm is None:
        if not _open_mmap():
            scriptOP.copyNumpyArray(np.zeros((MASK_H, MASK_W, 4), dtype=np.float32))
            return
    try:
        _mm.seek(0)
        header = _mm.read(HEADER_SIZE)
        frame_num = struct.unpack("<I", header[0:4])[0]
        if frame_num == _last_frame:
            return
        _last_frame = frame_num
        raw = _mm.read(MASK_W * MASK_H)
        mask = np.frombuffer(raw, dtype=np.uint8).reshape((MASK_H, MASK_W))
        mask_f = mask.astype(np.float32) / 255.0
        rgba = np.zeros((MASK_H, MASK_W, 4), dtype=np.float32)
        rgba[:,:,0] = rgba[:,:,1] = rgba[:,:,2] = rgba[:,:,3] = mask_f
        scriptOP.copyNumpyArray(rgba)
    except:
        _open_mmap()

def setup(scriptOP):
    _open_mmap()
'''
    print("  Inline mask reader script loaded")

# Point Script TOP to the callback DAT
try:
    body_mask.par.callbacks = 'segmentation_mask_reader'
except:
    pass

# Edge detection on body mask
edge_detect = ensure_op(ROOT + '/edge_detect', 'edgeTOP')
edge_detect.inputConnectors[0].connect(body_mask)
print("  Created: body_mask_top → edge_detect")

# Blur the edge for softer flame zone
edge_blur = ensure_op(ROOT + '/edge_blur', 'blurTOP')
edge_blur.par.size = 4.0
edge_blur.inputConnectors[0].connect(edge_detect)
print("  Created: edge_detect → edge_blur")


# ============================================================
# OSC INPUT CHAIN
# ============================================================
print("\n[3/8] Creating OSC input chain...")

# OSC In CHOP — receives /movement/* from movement_tracker.py
osc_body = ensure_op(ROOT + '/osc_body', 'oscinCHOP')
osc_body.par.port = 7000
print("  Created: osc_body (port 7000)")

# Constant CHOP for body tracking channels
body_channels = ensure_op(ROOT + '/body_channels', 'constantCHOP')
body_chan_names = [
    'lh_x', 'lh_y', 'rh_x', 'rh_y',
    'lh_height', 'rh_height',
    'hand_spread', 'body_height', 'head_x', 'head_y',
    'shoulder_tilt', 'motion_energy', 'tracking_active',
    'mask_active', 'num_people'
]
# Set channel names
body_channels.par.name0 = body_chan_names[0]
body_channels.par.value0 = 0
for i, name in enumerate(body_chan_names[1:], 1):
    try:
        setattr(body_channels.par, f'name{i}', name)
        setattr(body_channels.par, f'value{i}', 0)
    except:
        pass
print(f"  Created: body_channels ({len(body_chan_names)} channels)")

# OSC Body Receiver DAT
osc_recv_dat = ensure_op(ROOT + '/osc_body_receiver', 'chopexecuteDAT')
osc_recv_script_path = project.folder + '/touchdesigner/scripts/osc_body_receiver.py'
if os.path.exists(osc_recv_script_path):
    osc_recv_dat.par.file = osc_recv_script_path
    osc_recv_dat.par.syncfile = True
    print(f"  Loaded osc_body_receiver from file")
else:
    print("  WARNING: osc_body_receiver.py not found, load manually")
try:
    osc_recv_dat.par.chop = 'osc_body'
    osc_recv_dat.par.onoffton = False
    osc_recv_dat.par.offtoon = False
    osc_recv_dat.par.valuechange = True
    osc_recv_dat.par.active = True
except:
    pass


# ============================================================
# AUDIO ANALYSIS CHAIN
# ============================================================
print("\n[4/8] Creating audio analysis chain...")

# Audio Device In CHOP
audio_in = ensure_op(ROOT + '/audio_in', 'audiodeviceinCHOP')
print("  Created: audio_in (configure device manually)")

# Audio Spectrum CHOP
audio_spectrum = ensure_op(ROOT + '/audio_spectrum', 'audiospectrumCHOP')
audio_spectrum.inputConnectors[0].connect(audio_in)
print("  Created: audio_in → audio_spectrum")

# Constant CHOP for audio-reactive parameters
audio_params = ensure_op(ROOT + '/audio_params', 'constantCHOP')
audio_chan_names = [
    'bass_energy', 'bass_smooth',
    'mid_energy', 'mid_smooth',
    'high_energy', 'high_smooth',
    'onset', 'onset_trigger',
    'flame_intensity', 'particle_size', 'emission_rate',
    'turbulence', 'velocity', 'distortion',
    'sparkle', 'bloom_intensity',
    'burst_active', 'burst_decay'
]
audio_params.par.name0 = audio_chan_names[0]
audio_params.par.value0 = 0
for i, name in enumerate(audio_chan_names[1:], 1):
    try:
        setattr(audio_params.par, f'name{i}', name)
        setattr(audio_params.par, f'value{i}', 0)
    except:
        pass
print(f"  Created: audio_params ({len(audio_chan_names)} channels)")

# Audio Reactive Mapper DAT
audio_mapper_dat = ensure_op(ROOT + '/audio_reactive_mapper', 'chopexecuteDAT')
mapper_script_path = project.folder + '/touchdesigner/scripts/audio_reactive_mapper.py'
if os.path.exists(mapper_script_path):
    audio_mapper_dat.par.file = mapper_script_path
    audio_mapper_dat.par.syncfile = True
    print(f"  Loaded audio_reactive_mapper from file")
else:
    print("  WARNING: audio_reactive_mapper.py not found, load manually")
try:
    audio_mapper_dat.par.chop = 'audio_spectrum'
    audio_mapper_dat.par.valuechange = True
    audio_mapper_dat.par.active = True
except:
    pass


# ============================================================
# CHOP TO TOP CONVERTERS (for GLSL shader inputs)
# ============================================================
print("\n[5/8] Creating CHOP-to-TOP converters...")

# Motion energy → TOP texture for GLSL input 1
motion_top = ensure_op(ROOT + '/motion_energy_top', 'choptoTOP')
try:
    motion_top.par.chop = 'body_channels'
except:
    pass
print("  Created: body_channels → motion_energy_top (via chop par)")

# Audio energy → TOP texture for GLSL input 2
audio_top = ensure_op(ROOT + '/audio_energy_top', 'choptoTOP')
try:
    audio_top.par.chop = 'audio_params'
except:
    pass
print("  Created: audio_params → audio_energy_top (via chop par)")


# ============================================================
# NOISE LAYER (replaces Particle GPU — not available in TD 2022)
# Uses Noise TOP for extra turbulence / ember texture
# ============================================================
print("\n[6/8] Creating noise ember layer (TD 2022 workaround)...")

noise_embers = ensure_op(ROOT + '/noise_embers', 'noiseTOP')
noise_embers.par.resolutionw = 1280
noise_embers.par.resolutionh = 720
try:
    noise_embers.par.type = 'sparse'   # Sparse noise looks ember-like
    noise_embers.par.monochrome = True
    noise_embers.par.amp = 0.8
    noise_embers.par.offset = 0.2
    noise_embers.par.period = 30
    noise_embers.par.harmonics = 5
    noise_embers.par.rough = 0.6
    noise_embers.par.t1 = "absTime.seconds * 0.5"
    noise_embers.par.t2 = "absTime.seconds * 0.8"
except Exception as e:
    print(f"  Note: Some noise params may need manual setup: {e}")
print("  Created: noise_embers (1280x720, sparse noise)")


# ============================================================
# GLSL FIRE SHADER
# ============================================================
print("\n[7/8] Creating GLSL fire shader...")

# Text DAT for the shader code
shader_dat = ensure_op(ROOT + '/fire_aura_shader_code', 'textDAT')
shader_path = project.folder + '/touchdesigner/shaders/fire_aura.glsl'
if os.path.exists(shader_path):
    shader_dat.par.file = shader_path
    shader_dat.par.loadonstart = True
    shader_dat.par.syncfile = True
    print(f"  Loaded fire_aura.glsl from file")
else:
    print("  WARNING: fire_aura.glsl not found, load manually")

# GLSL TOP
fire_glsl = ensure_op(ROOT + '/fire_aura_glsl', 'glslTOP')
fire_glsl.par.resolutionw = 1280
fire_glsl.par.resolutionh = 720
try:
    fire_glsl.par.pixeldat = 'fire_aura_shader_code'
except:
    pass

# Connect GLSL inputs: 0=edge_blur, 1=motion_top, 2=audio_top
fire_glsl.inputConnectors[0].connect(edge_blur)
fire_glsl.inputConnectors[1].connect(motion_top)
fire_glsl.inputConnectors[2].connect(audio_top)
print("  Created: fire_aura_glsl (edge_blur + motion + audio → GLSL)")


# ============================================================
# COMPOSITING + POST-PROCESSING
# ============================================================
print("\n[8/8] Creating compositing chain...")

# Combine noise embers + GLSL flame via Composite (Add)
flame_layers = ensure_op(ROOT + '/flame_layers', 'compositeTOP')
flame_layers.inputConnectors[0].connect(fire_glsl)
flame_layers.inputConnectors[1].connect(noise_embers)
try:
    flame_layers.par.operand = 'add'
except:
    pass
print("  Created: fire_aura_glsl + noise_embers → flame_layers (Add)")

# Bloom workaround: Blur + Add composite (bloomTOP not in TD 2022)
bloom_blur = ensure_op(ROOT + '/bloom_blur', 'blurTOP')
bloom_blur.par.size = 12.0
bloom_blur.inputConnectors[0].connect(flame_layers)
print("  Created: flame_layers → bloom_blur (glow pass)")

bloom_post = ensure_op(ROOT + '/bloom_post', 'compositeTOP')
bloom_post.inputConnectors[0].connect(flame_layers)
bloom_post.inputConnectors[1].connect(bloom_blur)
try:
    bloom_post.par.operand = 'add'
    bloom_post.par.opacity2 = 0.5   # Blend glow at 50%
except:
    pass
print("  Created: flame_layers + bloom_blur → bloom_post (Add glow)")

# Burst flash overlay
burst_flash = ensure_op(ROOT + '/burst_flash', 'constantTOP')
burst_flash.par.resolutionw = 1280
burst_flash.par.resolutionh = 720
burst_flash.par.colorr = 1.0
burst_flash.par.colorg = 0.95
burst_flash.par.colorb = 0.8
burst_flash.par.alpha = 0.0
print("  Created: burst_flash (warm white, alpha=0)")

# Camera input
camera_in = ensure_op(ROOT + '/camera_in', 'videodeviceinTOP')
camera_in.par.resolutionw = 1280
camera_in.par.resolutionh = 720
print("  Created: camera_in (configure device manually)")

# Final composite: camera UNDER, aura OVER
final_comp = ensure_op(ROOT + '/final_composite', 'compositeTOP')
final_comp.inputConnectors[0].connect(camera_in)
final_comp.inputConnectors[1].connect(bloom_post)
final_comp.inputConnectors[2].connect(burst_flash)
try:
    final_comp.par.operand = 'over'
except:
    pass
print("  Created: camera_in + bloom_post + burst_flash → final_composite (Over)")

# Aura compositor Execute DAT (frame controller)
comp_dat = ensure_op(ROOT + '/aura_compositor', 'executeDAT')
comp_script_path = project.folder + '/touchdesigner/scripts/aura_compositor.py'
if os.path.exists(comp_script_path):
    comp_dat.par.file = comp_script_path
    comp_dat.par.syncfile = True
    print(f"  Loaded aura_compositor from file")
else:
    print("  WARNING: aura_compositor.py not found, load manually")
try:
    comp_dat.par.framestart = True
    comp_dat.par.active = True
except:
    pass

# Null TOP at the end for clean output
output_null = ensure_op(ROOT + '/output', 'nullTOP')
output_null.inputConnectors[0].connect(final_comp)
print("  Created: final_composite → output (Null TOP)")


# ============================================================
# LAYOUT (arrange operators visually)
# ============================================================
print("\n  Arranging operators...")

layout = {
    # Body mask chain (left column)
    'body_mask_top':              (-600, 400),
    'segmentation_mask_reader':   (-600, 500),
    'edge_detect':                (-400, 400),
    'edge_blur':                  (-200, 400),

    # OSC chain (bottom left)
    'osc_body':                   (-600, 100),
    'body_channels':              (-400, 100),
    'osc_body_receiver':          (-600, 0),

    # Audio chain (bottom)
    'audio_in':                   (-600, -200),
    'audio_spectrum':             (-400, -200),
    'audio_params':               (-200, -200),
    'audio_reactive_mapper':      (-400, -300),

    # Converters (middle)
    'motion_energy_top':          (-200, 200),
    'audio_energy_top':           (-200, 0),

    # Core effects (center)
    'noise_embers':               (100, 200),
    'fire_aura_glsl':             (100, 400),
    'fire_aura_shader_code':      (100, 500),

    # Compositing (right)
    'flame_layers':               (300, 400),
    'bloom_blur':                 (400, 300),
    'bloom_post':                 (500, 400),
    'burst_flash':                (500, 200),
    'camera_in':                  (500, 600),
    'final_composite':            (700, 400),
    'output':                     (900, 400),

    # Controller
    'aura_compositor':            (700, 200),
}

for name, (x, y) in layout.items():
    o = op(ROOT + '/' + name)
    if o is not None:
        o.nodeX = x
        o.nodeY = y

print("  Layout complete!")


# ============================================================
# DONE
# ============================================================
print("\n" + "=" * 60)
print("  PIPELINE BUILT SUCCESSFULLY")
print("=" * 60)
print("""
  Next steps:
  1. Configure 'camera_in' → select your webcam
  2. Configure 'audio_in' → select your DJ audio device
  3. Start movement_tracker.py externally:
     python python/movement_tracker.py --max-people 1
  4. Play music and dance!

  Manual checks:
  - body_mask_top should show white silhouette
  - edge_blur should show soft body outline
  - fire_aura_glsl should render flames
  - final_composite should show camera + fire aura
""")
