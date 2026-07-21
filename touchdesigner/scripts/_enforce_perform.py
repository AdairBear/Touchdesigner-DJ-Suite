# _enforce_perform.py -- TD-side: detect HISENSE by NAME, force Perform Mode
# onto it, verify, and report. Driven by perform_enforcer.sh. Idempotent.
import json, time, subprocess, re


def hisense_monitor():
    """Return (td_monitor_index, (w, h), method). Detect by NAME via
    system_profiler (TD's monitors[].description is empty on this machine), then
    match that display's resolution to a TD monitor. Falls back to the largest
    non-primary display if the name isn't found."""
    res = None
    try:
        out = subprocess.run(['/usr/sbin/system_profiler', 'SPDisplaysDataType'],
                             capture_output=True, text=True, timeout=12).stdout
        lines = out.splitlines()
        for i, ln in enumerate(lines):
            if 'hisense' in ln.lower() and ln.rstrip().endswith(':'):
                for j in range(i + 1, min(i + 12, len(lines))):
                    m = re.search(r'Resolution:\s*(\d+)\s*x\s*(\d+)', lines[j])
                    if m:
                        res = (int(m.group(1)), int(m.group(2)))
                        break
                break
    except Exception:
        pass
    if res:
        for mo in monitors:
            if mo.width == res[0] and mo.height == res[1]:
                return mo.index, res, 'name-match'
    cand = [mo for mo in monitors if not mo.isPrimary]
    if cand:
        mo = max(cand, key=lambda m: m.width * m.height)
        return mo.index, (mo.width, mo.height), 'fallback-largest'
    return None, None, 'none'


idx, res, method = hisense_monitor()
w = op('/project1/perform')
err = None
win_errors = []
active = False
isopen = False
win_monitor = None

try:
    if w is not None and idx is not None:
        w.par.monitor = idx                 # HISENSE, detected by NAME (not hardcoded)
        w.par.size = 'custom'
        w.par.winw = res[0]                 # concrete ints, no zero-resolving expr
        w.par.winh = res[1]
        w.par.winoffsetx = 0
        w.par.winoffsety = 0
        w.par.dpiscaling = 'native'
        w.par.setperform.pulse()
    ui.performMode = True
except Exception as e:
    err = str(e)
try:
    active = bool(ui.performMode)
except Exception as e:
    err = (err or '') + ' read:' + str(e)
if w is not None:
    isopen = bool(w.isOpen)
    win_monitor = w.par.monitor.eval()
    win_errors = [str(e) for e in w.errors()]

# on_hisense: the window's target monitor equals the detected HISENSE index.
on_hisense = (idx is not None and win_monitor == idx)
# fatal = a real window ERROR (the "Invalid window size" modal) -> stop, do NOT
# spam the modal. NOT-on-HISENSE / idx-None are transient (system_profiler can be
# slow during load) -> the enforcer keeps retrying and only CRITICALs on exhaustion.
fatal = bool(win_errors)

json.dump({'active': active, 'isOpen': isopen, 'on_hisense': on_hisense,
           'hisense_index': idx, 'hisense_res': res, 'detect_method': method,
           'window_monitor': win_monitor, 'win_errors': win_errors,
           'fatal': fatal, 'reason': 'enforcer', 'err': err, 'ts': time.time()},
          open('/tmp/td_perform_state.json', 'w'))
print('[_enforce_perform] active=%s on_hisense=%s idx=%s(%s) errors=%s fatal=%s'
      % (active, on_hisense, idx, method, win_errors, fatal))
