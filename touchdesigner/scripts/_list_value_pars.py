g = op('/project1/fire_aura_glsl')
print('\n=== CUSTOM PAGES & PARS ===')
for page in g.customPages:
    print(f'[{page.name}] pars:')
    for p in page.pars:
        try:
            v = p.eval()
        except Exception as e:
            v = 'ERR'
        print('  ', p.name, 'mode=', p.mode, 'expr=', repr(p.expr), 'val=', repr(p.val), 'eval=', v)

print('\n=== BUILT-IN VECTORS slots 0..9 ===')
for i in range(10):
    np = getattr(g.par, 'uniname' + str(i), None)
    vp = getattr(g.par, 'value' + str(i) + 'x',  None)
    name = np.val if np else '?'
    expr = vp.expr if vp else '-'
    print('  slot', i, ':', name, 'expr=', repr(expr))

print('\n=== DIRECT EVAL of value1 custom par (if it exists) ===')
for nm in ('value1','value1x','value2','value2x','value3x'):
    p = getattr(g.par, nm, None)
    if p is None:
        print('  ', nm, '= <no par>')
    else:
        print('  ', nm, 'mode=', p.mode, 'expr=', repr(p.expr), 'val=', repr(p.val))
