# _fix_aura.py — one-shot fixer, run from TD Textport
# exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/_fix_aura.py').read())
#
# Goals:
#   1. Wire the fire_aura_glsl Vectors page with the 10 named uniforms the
#      shader uses, each bound to a value1..value9 parameter.
#   2. Force-reload segmentation_mask_reader and aura_compositor DATs from disk.
#   3. Ensure final_composite operation = Over (bloom_post + burst_flash over camera_in).
#   4. Confirm syphonOut1 is active + correctly named.
#   5. Force-cook everything and print a compact render summary.


def _log(tag, msg):
    print('[fix] {}: {}'.format(tag, msg))


# ---------- 1. GLSL uniforms ----------
def _fix_glsl_uniforms():
    glsl = op('/project1/fire_aura_glsl')
    if glsl is None:
        _log('glsl', 'MISSING /project1/fire_aura_glsl')
        return
    # Uniform wiring: map each uniform name to a value parameter slot.
    # The aura_compositor writes into value1..value9 every frame.
    mapping = [
        ('uFlameIntensity', 1),
        ('uTurbulence',     2),
        ('uDistortion',     3),
        ('uSparkle',        4),
        ('uMotionEnergy',   5),
        ('uBassEnergy',     6),
        ('uMidEnergy',      7),
        ('uHighEnergy',     8),
        ('uBurstDecay',     9),
    ]
    # Vectors page on a GLSL TOP has uniformname1..uniformnameN paired with
    # value1..valueN. We set uniformnameK = name so the shader finds it.
    for name, idx in mapping:
        pname = 'uniformname{}'.format(idx)
        if hasattr(glsl.par, pname):
            try:
                setattr(glsl.par, pname, type('x', (), {})())  # no-op guard
            except Exception:
                pass
            try:
                p = getattr(glsl.par, pname)
                p.val = name
                _log('uniform', '{} <- {}'.format(pname, name))
            except Exception as e:
                _log('uniform-err', '{} {}'.format(pname, e))
        else:
            _log('uniform-missing', 'no par {} on fire_aura_glsl'.format(pname))
    # uTime: TD provides absolute time via uTime by default if declared.
    # If uTime uniform is still unassigned, bind slot 10 to a constant driven elsewhere.
    if hasattr(glsl.par, 'uniformname10'):
        try:
            glsl.par.uniformname10 = 'uTime'
            _log('uniform', 'uniformname10 <- uTime')
        except Exception as e:
            _log('uniform-err', 'uTime {}'.format(e))
    glsl.cook(force=True)
    errs = (glsl.errors() or '').strip()
    warns = (glsl.warnings() or '').strip()
    _log('glsl-state', 'res={}x{} err={} warn={}'.format(
        glsl.width, glsl.height, errs[:120], warns[:200]))


# ---------- 2. Reload file-backed DATs ----------
def _reload_dats():
    for path in ['/project1/segmentation_mask_reader',
                 '/project1/aura_compositor']:
        d = op(path)
        if d is None:
            _log('dat', 'MISSING ' + path)
            continue
        src = None
        try:
            if hasattr(d.par, 'file'):
                src = d.par.file.eval()
        except Exception:
            pass
        if not src:
            base = '/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/'
            src = base + path.split('/')[-1] + '.py'
        try:
            with open(src, 'r') as fh:
                d.text = fh.read()
            _log('dat-reload', '{} <- {} len={}'.format(path, src, len(d.text)))
        except Exception as e:
            _log('dat-reload-err', '{} {}'.format(path, e))


# ---------- 3. Final composite fix ----------
def _fix_final_composite():
    comp = op('/project1/final_composite')
    if comp is None:
        _log('comp', 'MISSING /project1/final_composite')
        return
    _log('comp-type', comp.type)
    # If it's a compositeTOP, ensure operand = 'over' and opacity params >0
    try:
        if hasattr(comp.par, 'operand'):
            comp.par.operand = 'over'
            _log('comp-op', 'operand=over')
    except Exception as e:
        _log('comp-op-err', e)
    # Make sure opacity1/2/3 are non-zero on a compTOP
    for i in (1, 2, 3, 4):
        pname = 'opacity' + str(i)
        if hasattr(comp.par, pname):
            try:
                getattr(comp.par, pname).val = 1.0
                _log('comp-par', '{}=1.0'.format(pname))
            except Exception:
                pass
    comp.cook(force=True)
    errs = (comp.errors() or '').strip()
    _log('comp-state', 'res={}x{} err={}'.format(
        comp.width, comp.height, errs[:120]))


# ---------- 4. Syphon output ----------
def _fix_syphon():
    sy = op('/project1/syphonOut1') or op('/project1/syphonspoutOut1')
    if sy is None:
        # Scan for any syphon/spout op
        root = op('/project1')
        if root is not None:
            for c in root.findChildren(depth=1):
                t = (c.type or '').lower()
                if 'syphon' in t or 'spout' in t:
                    sy = c
                    break
    if sy is None:
        _log('syphon', 'no syphon/spout TOP found under /project1')
        return
    _log('syphon-found', '{} type={}'.format(sy.path, sy.type))
    try:
        if hasattr(sy.par, 'active'):
            sy.par.active = True
        if hasattr(sy.par, 'sendername'):
            sy.par.sendername = 'TDSyphonSpoutOut'
    except Exception as e:
        _log('syphon-err', e)
    # Make sure its input is final_composite or output
    try:
        out_op = op('/project1/output') or op('/project1/final_composite')
        if out_op is not None and len(sy.inputs) == 0:
            sy.inputConnectors[0].connect(out_op)
            _log('syphon-wire', 'connected {} -> {}'.format(out_op.path, sy.path))
    except Exception as e:
        _log('syphon-wire-err', e)


# ---------- 5. Render summary ----------
def _summary():
    paths = [
        '/project1/body_mask_top',
        '/project1/fire_aura_glsl',
        '/project1/flame_layers',
        '/project1/bloom_post',
        '/project1/burst_flash',
        '/project1/camera_in',
        '/project1/final_composite',
        '/project1/output',
        '/project1/syphonOut1',
    ]
    print('[fix] --- summary ---')
    for p in paths:
        o = op(p)
        if o is None:
            print('  MISSING', p); continue
        print('  {:30s} {:>10s} {}x{} err={}'.format(
            p.split('/')[-1],
            o.type[:10],
            o.width, o.height,
            ((o.errors() or '').strip()[:60]) or 'none'))


def _run():
    print('[fix] === START ===')
    _fix_glsl_uniforms()
    _reload_dats()
    _fix_final_composite()
    _fix_syphon()
    _summary()
    print('[fix] === END ===')


_run()
