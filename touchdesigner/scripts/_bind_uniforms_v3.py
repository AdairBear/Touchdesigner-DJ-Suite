# Bind 9 audio/motion uniforms + uTime onto fire_aura_glsl Vectors page.
# Robust: works with uniname0..9 / value0x..value9x (confirmed exist).
g = op('/project1/fire_aura_glsl')

uniforms = [
    ('uFlameIntensity', "op('.').par.value1x"),
    ('uTurbulence',     "op('.').par.value2x"),
    ('uDistortion',     "op('.').par.value3x"),
    ('uSparkle',        "op('.').par.value4x"),
    ('uMotionEnergy',   "op('.').par.value5x"),
    ('uBassEnergy',     "op('.').par.value6x"),
    ('uMidEnergy',      "op('.').par.value7x"),
    ('uHighEnergy',     "op('.').par.value8x"),
    ('uBurstDecay',     "op('.').par.value9x"),
    ('uTime',           "absTime.seconds"),
]

missing = []
for i, (uname, expr) in enumerate(uniforms):
    name_par = getattr(g.par, f'uniname{i}', None)
    val_par  = getattr(g.par, f'value{i}x',  None)
    if name_par is None or val_par is None:
        missing.append((i, uname, 'MISSING PAR'))
        continue
    name_par.val = uname
    val_par.expr = expr
    val_par.mode = ParMode.EXPRESSION

# Blank any slot beyond 9 that we previously wrote, so there's no stale junk
for i in range(10, 12):
    np = getattr(g.par, f'uniname{i}', None)
    vp = getattr(g.par, f'value{i}x', None)
    if np is not None:
        np.val = ''
    if vp is not None:
        vp.mode = ParMode.CONSTANT
        vp.val = 0.0

g.cook(force=True)

print('\n=== UNIFORM BINDING v3 ===')
for i, (uname, expr) in enumerate(uniforms):
    np = getattr(g.par, f'uniname{i}', None)
    vp = getattr(g.par, f'value{i}x',  None)
    if np and vp:
        try:
            ev = vp.eval()
        except Exception as e:
            ev = f'ERR({e})'
        print(f'  slot {i:>2}: name={np.val!r:25s} mode={vp.mode} expr={vp.expr!r} eval={ev}')
    else:
        print(f'  slot {i:>2}: MISSING')
if missing:
    print('MISSING slots:', missing)
print('errors:', g.errors() or 'none')
print('warnings:', g.warnings() or 'none')
