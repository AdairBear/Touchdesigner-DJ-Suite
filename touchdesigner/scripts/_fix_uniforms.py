# Register 10 scalar uniforms on fire_aura_glsl's Vectors page:
#   slot 0..8 → audio/motion custom floats value1..value9
#   slot 9     → uTime bound to absTime.seconds
g = op('/project1/fire_aura_glsl')

uniforms = [
    ('uFlameIntensity', 'value1'),
    ('uTurbulence',     'value2'),
    ('uDistortion',     'value3'),
    ('uSparkle',        'value4'),
    ('uMotionEnergy',   'value5'),
    ('uBassEnergy',     'value6'),
    ('uMidEnergy',      'value7'),
    ('uHighEnergy',     'value8'),
    ('uBurstDecay',     'value9'),
]

for i, (uname, src_par) in enumerate(uniforms):
    name_par = getattr(g.par, f'uniname{i}', None)
    val_par  = getattr(g.par, f'value{i}x',  None)  # x-component of the value{i} group
    if name_par is None or val_par is None:
        print(f'MISSING par uniname{i} / value{i}x')
        continue
    name_par.val = uname
    # Reference the x-component of the custom float group (value1 → value1x)
    val_par.expr = f"op('.').par.{src_par}x"
    val_par.mode = ParMode.EXPRESSION

# Time slot (slot 9): uTime bound to absTime.seconds
i = 9
name_par = getattr(g.par, f'uniname{i}', None)
val_par  = getattr(g.par, f'value{i}x',  None)
if name_par and val_par:
    name_par.val = 'uTime'
    val_par.expr = 'absTime.seconds'
    val_par.mode = ParMode.EXPRESSION

g.cook(force=True)
print('Bound uniforms (10):', [u for u, _ in uniforms] + ['uTime'])
print('Errors:', g.errors() or 'none')
print('Warnings:', g.warnings() or 'none')
