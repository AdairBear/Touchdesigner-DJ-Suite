# react_selftest.py -- runs INSIDE TouchDesigner. Proves the fx_react bus fires.
#
# Play a track with real drums FIRST (the test needs transients), then:
#   bridge:   python3 touchdesigner/scripts/bridge_send.py --file touchdesigner/scripts/react_selftest.py
#   textport: exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/react_selftest.py').read())
#
# It samples fx_react once per frame for SAMPLE_FRAMES frames (scheduled with
# run(..., delayFrames=i), so the timeline keeps playing), then prints a verdict
# in the Textport and writes it to <repo>/.bridge/react_selftest.json.
# Read-only: it changes no parameter and applies no profile.
import json

SAMPLE_FRAMES = 240  # ~4 s at 60 fps
_KEY = "_react_selftest"
_OUT = "/Users/thomasadair/projects/touchdesigner-dj-suite/.bridge/react_selftest.json"
_CHANS = ("kick", "snare", "kick_gate", "snare_gate", "bass", "mid", "high",
          "energy_slow", "energy_fast", "drama")

_SAMPLE = '''
r = op('/project1/fx_react')
buf = op('/project1').fetch(%r, None, search=False)
if r is not None and buf is not None:
    buf.append({c: (float(r[c].eval()) if r[c] is not None else None) for c in %r})
''' % (_KEY, _CHANS)

_SUMMARY = '''
import json
buf = op('/project1').fetch(%r, [], search=False) or []
op('/project1').unstore(%r)
def edges(ch):
    n, prev = 0, 0.0
    for s in buf:
        v = s.get(ch) or 0.0
        if v > 0.5 and prev <= 0.5:
            n += 1
        prev = v
    return n
def width(ch, thr):
    runs, cur = [], 0
    for s in buf:
        if (s.get(ch) or 0.0) > thr:
            cur += 1
        elif cur:
            runs.append(cur); cur = 0
    return round(sum(runs) / len(runs), 1) if runs else 0.0
ef = [s.get('energy_fast') or 0.0 for s in buf]
res = {
    'frames': len(buf),
    'kick_gate_hits': edges('kick_gate'),
    'snare_gate_hits': edges('snare_gate'),
    'kick_gate_width_frames': width('kick_gate', 0.5),
    'kick_env_width_frames': width('kick', 0.05),
    'energy_fast_min': round(min(ef), 3) if ef else None,
    'energy_fast_max': round(max(ef), 3) if ef else None,
    'drama_fraction': round(sum(s.get('drama') or 0.0 for s in buf) / max(1, len(buf)), 3),
    'bass_max': max((s.get('bass') or 0.0) for s in buf) if buf else None,
}
problems = []
if not buf:
    problems.append('no samples -- fx_react missing? run install_react_bus.py')
elif (res['bass_max'] or 0.0) <= 1e-6:
    problems.append('no audio reaching fx_audio_bands (bass_max=0) -- check audio_in device / play a track')
else:
    if res['kick_gate_hits'] < 2:
        problems.append('kick_gate fired %%d times in %%d frames (want >= 2)' %% (res['kick_gate_hits'], res['frames']))
    if res['energy_fast_max'] - res['energy_fast_min'] < 0.1:
        problems.append('energy_fast barely moved (%%s..%%s) -- still DC-like' %% (res['energy_fast_min'], res['energy_fast_max']))
    if res['kick_gate_hits'] and res['kick_env_width_frames'] and res['kick_gate_width_frames'] > res['kick_env_width_frames']:
        problems.append('gate pulses are not shorter than the kick envelope')
res['verdict'] = 'PASS' if not problems else 'FAIL'
res['problems'] = problems
open(%r, 'w').write(json.dumps(res, indent=2))
print('[react_selftest]', res['verdict'], json.dumps(res))
''' % (_KEY, _KEY, _OUT)

if op("/project1/fx_react") is None:  # noqa: F821 - TD global
    print("[react_selftest] FAIL fx_react missing -- run install_react_bus.py first")
else:
    op("/project1").store(_KEY, [])  # noqa: F821
    for _i in range(1, SAMPLE_FRAMES + 1):
        run(_SAMPLE, delayFrames=_i)  # noqa: F821
    run(_SUMMARY, delayFrames=SAMPLE_FRAMES + 2)  # noqa: F821
    print("[react_selftest] sampling fx_react for %d frames; verdict follows in the "
          "Textport and %s" % (SAMPLE_FRAMES, _OUT))
