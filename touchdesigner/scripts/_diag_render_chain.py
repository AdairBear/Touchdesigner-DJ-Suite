# _diag_render_chain.py
# Run from TD textport:
#   exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/_diag_render_chain.py').read())
#
# Dumps state of the render pipeline -> syphonOut chain.
# Goal: find why OBS Syphon Client is frozen / no graphics.

chain = [
    'body_mask_top', 'edge_detect', 'edge_blur',
    'noise_embers',
    'motion_energy_top', 'audio_energy_top',
    'fire_aura_shader_code',
    'fire_aura_glsl',
    'flame_layers',
    'bloom_blur',
    'bloom_post',
    'burst_flash',
    'camera_in',
    'final_composite',
    'output',
]

print('\n=== RENDER CHAIN STATE ===')
for n in chain:
    o = op('/project1/' + n)
    if o is None:
        print('  ' + n + ': MISSING')
        continue
    try:
        errs = (o.errors() or '').strip()
    except Exception:
        errs = ''
    try:
        warns = (o.warnings() or '').strip()
    except Exception:
        warns = ''
    try:
        w = o.width
        h = o.height
    except Exception:
        w = h = '?'
    # Input wiring
    try:
        ins = []
        for i, ic in enumerate(o.inputConnectors):
            src = None
            try:
                if ic.connections:
                    src = ic.connections[0].owner.name
            except Exception:
                pass
            ins.append(str(i) + '=' + (src or '-'))
        inputs_s = ','.join(ins) if ins else 'none'
    except Exception:
        inputs_s = '?'
    try:
        bypass = bool(o.par.bypass.val) if hasattr(o.par, 'bypass') else False
    except Exception:
        bypass = False
    print('  ' + n + ' | res=' + str(w) + 'x' + str(h) +
          ' | in=' + inputs_s +
          ' | bypass=' + str(bypass) +
          (' | ERR=' + errs[:80] if errs else '') +
          (' | WARN=' + warns[:80] if warns else ''))

# Find all syphon-ish ops under /project1
print('\n=== SYPHON OUTPUT CANDIDATES ===')
root = op('/project1')
if root is not None:
    found_any = False
    for child in root.children:
        tname = (child.OPType or '').lower()
        nm = (child.name or '').lower()
        if 'syphon' in tname or 'syphon' in nm or 'spout' in tname or 'spout' in nm:
            found_any = True
            try:
                errs = (child.errors() or '').strip()
            except Exception:
                errs = ''
            try:
                warns = (child.warnings() or '').strip()
            except Exception:
                warns = ''
            # Input
            src = 'NOTHING CONNECTED'
            try:
                if child.inputConnectors and child.inputConnectors[0].connections:
                    src = child.inputConnectors[0].connections[0].owner.path
            except Exception:
                src = '<err>'
            # Key pars
            pars = {}
            for pn in ('active', 'sendername', 'senderName', 'sendername0'):
                try:
                    if hasattr(child.par, pn):
                        pars[pn] = getattr(child.par, pn).val
                except Exception:
                    pass
            print('  ' + child.path + ' (type=' + child.OPType + ')')
            print('    in0 <- ' + src)
            print('    pars=' + str(pars))
            print('    res=' + str(getattr(child, 'width', '?')) + 'x' + str(getattr(child, 'height', '?')))
            if errs:
                print('    ERR=' + errs[:200])
            if warns:
                print('    WARN=' + warns[:200])
    if not found_any:
        print('  NO SYPHON/SPOUT OPS FOUND under /project1')

# Any op with an error under /project1
print('\n=== OPERATORS WITH ERRORS ===')
bad = []
if root is not None:
    for child in root.children:
        try:
            e = (child.errors() or '').strip()
            if e:
                bad.append((child.path, e[:160]))
        except Exception:
            pass
print('  count: ' + str(len(bad)))
for p, m in bad:
    print('  ' + p + ': ' + m)

print('\n=== DONE ===')
