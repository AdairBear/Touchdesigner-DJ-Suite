# apply_alpha_fix.py -- make TD's Syphon output alpha-transparent except where
# graphics are drawn, so OBS can layer Syphon Client OVER Link Camera without a
# black box covering the camera. alpha = max(R,G,B) (not luminance -> keeps
# blue/purple/cyan graphics opaque). Idempotent. Does NOT wire camera_in.
#   exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/apply_alpha_fix.py').read())
import json
out = {}
p = op('/project1')
src = op('/project1/fx_out')          # last node before syphonOut1
sy = op('/project1/syphonOut1')

_SHADER = '''out vec4 fragColor;
void main()
{
    vec4 c = texture(sTD2DInputs[0], vUV.st);
    float a = max(c.r, max(c.g, c.b));   // alpha = brightest channel: 0 on black, keeps colored graphics
    a = a * a;                           // gamma: faint haze -> fully transparent, keep bright graphics
    fragColor = TDOutputSwizzle(vec4(c.rgb, a));
}
'''

# --- GLSL max-channel alpha (preferred) --------------------------------------
dat = op('/project1/syphon_alpha_glsl') or p.create(textDAT, 'syphon_alpha_glsl')
dat.text = _SHADER
dat.nodeX, dat.nodeY = 1300, 300
ga = op('/project1/syphon_alpha') or p.create(glslTOP, 'syphon_alpha')
ga.nodeX, ga.nodeY = 1300, 175
ga.par.pixeldat = 'syphon_alpha_glsl'
ga.setInputs([src])
ga.cook(force=True)
errs = [str(e) for e in ga.errors()]

use = ga
if errs:  # GLSL failed to compile -> fallback: Reorder TOP alpha=luminance
    out['glsl_errors'] = errs
    ro = op('/project1/syphon_alpha_ro') or p.create(reorderTOP, 'syphon_alpha_ro')
    ro.nodeX, ro.nodeY = 1300, 60
    ro.setInputs([src])
    # set output alpha = input luminance (menu value 'lum1' in TD reorder)
    for pn in ('outputalpha',):
        if hasattr(ro.par, pn):
            try: ro.par[pn] = 'lum1'
            except Exception: pass
    ro.cook(force=True)
    use = ro
    out['fallback'] = 'reorder luminance'

# --- wire syphonOut1 <- alpha node -------------------------------------------
sy.setInputs([use])
sy.cook(force=True)
ga.cook(force=True)

# --- verify: alpha varies (0 on empty, >0 on graphics) -----------------------
a = use.numpyArray()  # HxWx4 float
alpha = a[..., 3]
rgb = a[..., :3]
out['alpha_node'] = use.name
out['alpha_min'] = round(float(alpha.min()), 4)
out['alpha_max'] = round(float(alpha.max()), 4)
out['alpha_mean'] = round(float(alpha.mean()), 4)
out['transparent_frac'] = round(float((alpha < 0.02).mean()), 3)   # fraction fully see-through
out['graphics_frac'] = round(float((alpha > 0.1).mean()), 3)       # fraction showing graphics
out['syphon_in'] = [i.name for i in sy.inputs if i]
out['alpha_cook_ms'] = round(use.cookTime, 3)
out['perf_cook_ms'] = round(op('/project1/perform').cookTime, 3)
out['bmt_cook_ms'] = round(op('/project1/body_mask_top').cookTime, 3)
out['sy_active'] = sy.par.active.eval()
json.dump(out, open('/tmp/td_alpha.json', 'w'), indent=2, default=str)

# save to fresh path -> operator cp's to canonical
try:
    import os
    fp = '/Users/thomasadair/Desktop/_dj_alpha.toe'
    if os.path.exists(fp): os.remove(fp)
    project.save(fp)
    print('[alpha] SAVED %s -> cp to DJ_Graphics_LIVE.toe' % fp)
except Exception as e:
    print('[alpha] save failed:', e)
print('[alpha] done:', json.dumps(out))
