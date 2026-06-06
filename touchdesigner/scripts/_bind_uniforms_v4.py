# v4: correct mapping.
# aura_compositor.py writes to glsl.par.value1..value9 (Vectors slots 1..9).
# So audio uniforms must live on slots 1..9, and uTime takes slot 0.
g = op('/project1/fire_aura_glsl')

# slot 0 = uTime (expression)
# slots 1..9 = audio/motion uniforms (constant mode; compositor writes every frame)
layout = [
    (0, 'uTime',           'expr', 'absTime.seconds'),
    (1, 'uFlameIntensity', 'const', 0.5),
    (2, 'uTurbulence',     'const', 0.3),
    (3, 'uDistortion',     'const', 0.2),
    (4, 'uSparkle',        'const', 0.0),
    (5, 'uMotionEnergy',   'const', 0.0),
    (6, 'uBassEnergy',     'const', 0.0),
    (7, 'uMidEnergy',      'const', 0.0),
    (8, 'uHighEnergy',     'const', 0.0),
    (9, 'uBurstDecay',     'const', 0.0),
]

for i, uname, mode_kind, payload in layout:
    name_par = getattr(g.par, 'uniname' + str(i), None)
    val_par  = getattr(g.par, 'value' + str(i) + 'x', None)
    if name_par is None or val_par is None:
        print('MISSING slot', i)
        continue
    name_par.val = uname
    if mode_kind == 'expr':
        val_par.expr = payload
        val_par.mode = ParMode.EXPRESSION
    else:
        val_par.mode = ParMode.CONSTANT
        val_par.expr = ''
        val_par.val  = float(payload)

# clear slots 10+ so there's no leftover
for i in range(10, 12):
    np = getattr(g.par, 'uniname' + str(i), None)
    vp = getattr(g.par, 'value' + str(i) + 'x', None)
    if np is not None: np.val = ''
    if vp is not None:
        vp.mode = ParMode.CONSTANT
        vp.expr = ''
        vp.val = 0.0

g.cook(force=True)

print('\n=== UNIFORM BINDING v4 ===')
for i in range(10):
    np = getattr(g.par, 'uniname' + str(i), None)
    vp = getattr(g.par, 'value' + str(i) + 'x', None)
    if np and vp:
        try: ev = vp.eval()
        except Exception as e: ev = 'ERR'
        print('  slot', i, ':', repr(np.val), 'mode=', vp.mode, 'expr=', repr(vp.expr), 'val=', vp.val, 'eval=', ev)
print('errors:', g.errors() or 'none')
print('warnings:', g.warnings() or 'none')
