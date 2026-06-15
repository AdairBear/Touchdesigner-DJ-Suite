g = op('/project1/fire_aura_glsl')
for i in range(12):
    np = getattr(g.par, f'uniname{i}', None)
    vp = getattr(g.par, f'value{i}x',  None)
    print(f'slot {i}: name={np.val if np else "NO PAR"} | valueXmode={vp.mode if vp else "NO PAR"} | expr={vp.expr if vp else "-"} | eval={vp.eval() if vp else "-"}')
