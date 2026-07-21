# _verify_perform.py -- read back the Perform Mode config to /tmp (no windows opened).
#   exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/_verify_perform.py').read())
import json
out = {}
w = op('/project1/perform')
if w is None:
    out['perform'] = None
else:
    out['perform'] = {
        'winop': str(w.par.winop.eval()),
        'winop_valid': op(w.par.winop.eval()) is not None if w.par.winop.eval() else False,
        'justifyoffsetto': str(w.par.justifyoffsetto.eval()),
        'monitor': w.par.monitor.eval(),
        'size': str(w.par.size.eval()),
        'borders': w.par.borders.eval(),
        'cursorvisible': str(w.par.cursorvisible.eval()),
        'closeescape': w.par.closeescape.eval(),
        'isOpen': getattr(w, 'isOpen', None),
    }
try:
    pw = project.performWindow
    out['project.performWindow'] = None if pw is None else pw.path
except Exception as e:
    out['performWindow_err'] = str(e)

d = op('/project1/perform_autostart')
if d is None:
    out['autostart'] = None
else:
    out['autostart'] = {
        'type': d.type,
        'start_par': d.par.start.eval() if hasattr(d.par, 'start') else 'NO_START_PAR',
        'active_par': d.par.active.eval() if hasattr(d.par, 'active') else None,
        'has_onStart': 'def onStart' in d.text,
    }
src = op('/project1/final_composite')
out['final_composite'] = None if src is None else {'w': src.width, 'h': src.height, 'cooked': src.cookedThisFrame}
with open('/tmp/td_perform_verify.json', 'w') as f:
    json.dump(out, f, indent=2)
print('[_verify_perform] wrote /tmp/td_perform_verify.json')
