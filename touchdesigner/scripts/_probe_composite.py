# _probe_composite.py — one-shot probe of final_composite and related ops.
# exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/_probe_composite.py').read())

def _dump(path):
    o = op(path)
    if o is None:
        print('[probe] MISSING', path)
        return
    print('[probe] ===', path, '===')
    print('  type:', o.type, '| family:', o.family, '| res:', o.width, 'x', o.height)
    print('  inputs:')
    for i, c in enumerate(o.inputs):
        print('    in', i, '<-', (c.path if c is not None else 'NONE'))
    print('  pars (non-default):')
    for p in o.pars():
        try:
            v = p.eval()
            d = p.default
            if v != d:
                print('    ', p.name, '=', repr(v), '(default', repr(d), ')')
        except Exception:
            pass
    errs = (o.errors() or '').strip()
    if errs:
        print('  errors:', errs[:300])
    warns = (o.warnings() or '').strip()
    if warns:
        print('  warnings:', warns[:300])

for p in ['/project1/final_composite',
          '/project1/bloom_post',
          '/project1/burst_flash',
          '/project1/camera_in',
          '/project1/syphonOut1',
          '/project1/output']:
    _dump(p)

# Also look for Syphon ops by scanning the family
print('[probe] --- syphon scan ---')
root = op('/project1')
if root is not None:
    for c in root.findChildren(depth=1):
        if 'syphon' in (c.type or '').lower() or 'spout' in (c.type or '').lower():
            print('  found', c.path, 'type=', c.type, 'active=', getattr(c.par, 'active', None))
