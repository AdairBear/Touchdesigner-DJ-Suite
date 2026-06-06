# build_continue.py — Continuation from where build_aura_pipeline.py errored
# Run: exec(open(project.folder + '/touchdesigner/scripts/build_continue.py').read())
import os

ROOT = '/project1'

def ensure_op(path, optype):
    name = path.split('/')[-1]
    parent_path = '/'.join(path.split('/')[:-1])
    parent = op(parent_path)
    existing = op(path)
    if existing is not None:
        return existing
    return parent.create(optype, name)

print("=" * 50)
print("  Continuation: Steps 5-8")
print("=" * 50)

# ---- Step 5: CHOP-to-TOP converters ----
print("\n[5] CHOP-to-TOP converters...")
motion_top = ensure_op(ROOT + '/motion_energy_top', 'choptoTOP')
try:
    motion_top.par.chop = 'body_channels'
except:
    pass
print("  motion_energy_top OK")

audio_top = ensure_op(ROOT + '/audio_energy_top', 'choptoTOP')
try:
    audio_top.par.chop = 'audio_params'
except:
    pass
print("  audio_energy_top OK")

# ---- Step 6: Noise ember layer (TD 2022 workaround for particles) ----
print("\n[6] Noise ember layer...")
noise_embers = ensure_op(ROOT + '/noise_embers', 'noiseTOP')
noise_embers.par.resolutionw = 1280
noise_embers.par.resolutionh = 720
try:
    noise_embers.par.monochrome = True
    noise_embers.par.amp = 0.8
    noise_embers.par.offset = 0.2
except:
    pass
print("  noise_embers OK")

# ---- Step 7: GLSL fire shader ----
print("\n[7] GLSL fire shader...")
shader_dat = ensure_op(ROOT + '/fire_aura_shader_code', 'textDAT')
shader_path = project.folder + '/touchdesigner/shaders/fire_aura.glsl'
if os.path.exists(shader_path):
    shader_dat.par.file = shader_path
    shader_dat.par.loadonstart = True
    shader_dat.par.syncfile = True
    print("  Loaded fire_aura.glsl")

fire_glsl = ensure_op(ROOT + '/fire_aura_glsl', 'glslTOP')
fire_glsl.par.resolutionw = 1280
fire_glsl.par.resolutionh = 720
try:
    fire_glsl.par.pixeldat = 'fire_aura_shader_code'
except:
    pass

# Get references to earlier ops
edge_blur = op(ROOT + '/edge_blur')
if edge_blur:
    fire_glsl.inputConnectors[0].connect(edge_blur)
fire_glsl.inputConnectors[1].connect(motion_top)
fire_glsl.inputConnectors[2].connect(audio_top)
print("  fire_aura_glsl wired")

# ---- Step 8: Compositing chain ----
print("\n[8] Compositing chain...")

# Flame layers: GLSL + noise embers
flame_layers = ensure_op(ROOT + '/flame_layers', 'compositeTOP')
flame_layers.inputConnectors[0].connect(fire_glsl)
flame_layers.inputConnectors[1].connect(noise_embers)
try:
    flame_layers.par.operand = 'add'
except:
    pass
print("  flame_layers OK")

# Bloom workaround: blur + add
bloom_blur = ensure_op(ROOT + '/bloom_blur', 'blurTOP')
bloom_blur.par.size = 12.0
bloom_blur.inputConnectors[0].connect(flame_layers)

bloom_post = ensure_op(ROOT + '/bloom_post', 'compositeTOP')
bloom_post.inputConnectors[0].connect(flame_layers)
bloom_post.inputConnectors[1].connect(bloom_blur)
try:
    bloom_post.par.operand = 'add'
    bloom_post.par.opacity2 = 0.5
except:
    pass
print("  bloom (blur+add) OK")

# Burst flash
burst_flash = ensure_op(ROOT + '/burst_flash', 'constantTOP')
burst_flash.par.resolutionw = 1280
burst_flash.par.resolutionh = 720
burst_flash.par.colorr = 1.0
burst_flash.par.colorg = 0.95
burst_flash.par.colorb = 0.8
burst_flash.par.alpha = 0.0
print("  burst_flash OK")

# Camera input
camera_in = ensure_op(ROOT + '/camera_in', 'videodeviceinTOP')
camera_in.par.resolutionw = 1280
camera_in.par.resolutionh = 720
print("  camera_in OK")

# Final composite
final_comp = ensure_op(ROOT + '/final_composite', 'compositeTOP')
final_comp.inputConnectors[0].connect(camera_in)
final_comp.inputConnectors[1].connect(bloom_post)
final_comp.inputConnectors[2].connect(burst_flash)
try:
    final_comp.par.operand = 'over'
except:
    pass
print("  final_composite OK")

# Aura compositor Execute DAT
comp_dat = ensure_op(ROOT + '/aura_compositor', 'executeDAT')
comp_path = project.folder + '/touchdesigner/scripts/aura_compositor.py'
if os.path.exists(comp_path):
    comp_dat.par.file = comp_path
    comp_dat.par.syncfile = True
    print("  Loaded aura_compositor")
try:
    comp_dat.par.framestart = True
    comp_dat.par.active = True
except:
    pass

# Output null
output_null = ensure_op(ROOT + '/output', 'nullTOP')
output_null.inputConnectors[0].connect(final_comp)
print("  output OK")

# ---- Layout ----
print("\n  Arranging layout...")
layout = {
    'body_mask_top': (-600, 400),
    'segmentation_mask_reader': (-600, 500),
    'edge_detect': (-400, 400),
    'edge_blur': (-200, 400),
    'osc_body': (-600, 100),
    'body_channels': (-400, 100),
    'osc_body_receiver': (-600, 0),
    'audio_in': (-600, -200),
    'audio_spectrum': (-400, -200),
    'audio_params': (-200, -200),
    'audio_reactive_mapper': (-400, -300),
    'motion_energy_top': (-200, 200),
    'audio_energy_top': (-200, 0),
    'noise_embers': (100, 200),
    'fire_aura_glsl': (100, 400),
    'fire_aura_shader_code': (100, 500),
    'flame_layers': (300, 400),
    'bloom_blur': (400, 300),
    'bloom_post': (500, 400),
    'burst_flash': (500, 200),
    'camera_in': (500, 600),
    'final_composite': (700, 400),
    'output': (900, 400),
    'aura_compositor': (700, 200),
}
for name, (x, y) in layout.items():
    o = op(ROOT + '/' + name)
    if o is not None:
        o.nodeX = x
        o.nodeY = y

print("\n" + "=" * 50)
print("  PIPELINE COMPLETE!")
print("=" * 50)
