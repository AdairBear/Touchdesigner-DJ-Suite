# apply_look_pass.py -- WS2 envelope tuning + WS3 palette (Thomas's direction:
# CYAN -> ORANGE -> PURPLE, LFO sweep + kick-triggered discrete jumps). Idempotent.
# Run in TD Textport:
#   exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/apply_look_pass.py').read())
import json
out = {'before': {}, 'after': {}}

ke = op('/project1/fx_kick_env')
se = op('/project1/fx_snare_env')
lh = op('/project1/fx_lfo_hue')
pt = op('/project1/fx_palette_table')
pe = op('/project1/fx_palette_engine')
pe_cb = op('/project1/fx_palette_engine_cb')

out['before'] = {'kick_release': ke.par.release.eval(), 'snare_release': se.par.release.eval(),
                 'lfo_hue_freq': lh.par.frequency.eval(), 'palette_rows': pt.numRows}

# --- WS2: envelopes (kick decay 80ms transient, snare 100ms) -----------------
ke.par.release = 0.08
se.par.release = 0.10
# LFO hue drift underneath (subtle; the palette engine now carries the main sweep)
lh.par.frequency = 0.03

# --- WS3: 3 anchors CYAN -> ORANGE -> PURPLE ---------------------------------
# hex: cyan #00E5FF, orange #FF8A00, purple #8A2BE2. Each row = primary + secondary
# (secondary = the NEXT anchor) so both channels sweep through all three.
CYAN   = (0.000, 0.898, 1.000)
ORANGE = (1.000, 0.541, 0.000)
PURPLE = (0.541, 0.169, 0.886)
PALETTE = [
    CYAN   + ORANGE,   # cyan  -> (blends toward) orange
    ORANGE + PURPLE,   # orange-> purple
    PURPLE + CYAN,     # purple-> cyan
]
pt.clear()
for row in PALETTE:
    pt.appendRow(['%.4f' % v for v in row])

# --- WS3: palette engine = continuous sweep + kick-triggered discrete jump ---
# Time drives a smooth sweep between the 3 anchors (the "LFO cycling"); a kick
# rising-edge on fx_kick_env snaps the index forward one anchor (discrete jump).
_ENGINE = r'''# fx_palette_engine -- CYAN->ORANGE->PURPLE sweep.
# KICK  = discrete jump to next anchor (rising edge on fx_kick_env).
# SNARE = brightness POP (multiplies palette by fx_snare_env envelope) -- a
#         distinct percussive luminance flash, independent of the kick color jump.
_kick_jump = 0
_kick_prev = 0.0

def onCook(scriptOp):
    global _kick_jump, _kick_prev
    scriptOp.clear()
    tbl = op('fx_palette_table')
    names = ('primaryR','primaryG','primaryB','secondaryR','secondaryG','secondaryB')
    if tbl is None or tbl.numRows == 0:
        for nm in names:
            scriptOp.appendChan(nm).vals = [1.0]
        return
    n = tbl.numRows
    # kick rising edge -> discrete jump to the next anchor
    ke = op('fx_kick_env')
    kv = 0.0
    if ke is not None and ke.numChans > 0:
        try:
            kv = ke['bass'].eval()
        except Exception:
            kv = ke[0].eval()
    if kv > 0.5 and _kick_prev <= 0.5:
        _kick_jump += 1
    _kick_prev = kv
    # SNARE brightness pop -- fx_snare_env is already a decaying 0..1 envelope
    # (attack 3ms / release 100ms), so just read it and boost luminance.
    se = op('fx_snare_env')
    sv = 0.0
    if se is not None and se.numChans > 0:
        try:
            sv = se['high'].eval()
        except Exception:
            sv = se[0].eval()
    bright = 1.0 + sv * 0.8   # up to +80% flash on a snare, decays with the envelope
    # underlying continuous time sweep (seconds-per-anchor); + kick jumps
    period = 45.0
    pos = (absTime.seconds / period) + _kick_jump
    idx = int(pos) % n
    nxt = (idx + 1) % n
    frac = pos - int(pos)
    f = frac   # LINEAR crossfade: equal dwell on every anchor. (Was smoothstep,
               # which eased at the endpoints and rushed the middle -- so the
               # middle anchor, ORANGE, flashed by unseen, exactly like a sine LFO.)
    def cell(r, c):
        try:
            return float(tbl[r, c].val)
        except Exception:
            return 0.0
    for col, nm in enumerate(names):
        a = cell(idx, col)
        b = cell(nxt, col)
        scriptOp.appendChan(nm).vals = [(a + (b - a) * f) * bright]   # snare pop
    return
'''
if pe_cb is not None:
    pe_cb.text = _ENGINE
if pe is not None:
    pe.cook(force=True)

# --- Issue 1 fix: palette was multiplied over a CYAN base (base R=0), so orange
# and purple (which need red) rendered as green / murky blue -- the anchors never
# showed true. Desaturate the base before the palette multiply so it has R,G,B to
# tint. `saturationmult` is the aesthetic dial: lower = purer palette colors,
# higher = more of the original cyan character. (NOT an LFO clamp -- the engine
# already reaches all 3 anchors; verified fx_palette_engine hits purple.)
_fc = op('/project1/final_composite')
_pa = op('/project1/fx_palette_apply')
if _fc is not None and _pa is not None:
    _mono = op('/project1/fx_palette_mono') or op('/project1').create(hsvadjustTOP, 'fx_palette_mono')
    _mono.nodeX, _mono.nodeY = _fc.nodeX + 120, _fc.nodeY - 130
    if hasattr(_mono.par, 'saturationmult'):
        _mono.par.saturationmult = 0.20   # lower -> orange's red survives the tint better
    _mono.inputConnectors[0].connect(_fc)
    _pa.inputConnectors[0].connect(_mono)   # final_composite -> mono -> palette multiply
    _mono.cook(force=True)
    out['mono_saturationmult'] = _mono.par.saturationmult.eval() if hasattr(_mono.par, 'saturationmult') else None
    out['mono_wired'] = [i.path for i in _pa.inputs]

out['after'] = {'kick_release': ke.par.release.eval(), 'snare_release': se.par.release.eval(),
                'lfo_hue_freq': lh.par.frequency.eval(), 'palette_rows': pt.numRows,
                'engine_has_kickjump': ('_kick_jump' in pe_cb.text) if pe_cb else None,
                'palette_engine_chans': {c.name: round(c.eval(), 3) for c in pe.chans()} if pe else None}
# --- PERF: bass-dependent hitching. audio_spectrum was outputmenu=matchtofrequency
# (22050-sample output) with fftsize=8192 -> a ~1s FFT + huge spectrum every frame,
# the cost that scales with low-band content. Shrink it: visual bands need ~256 bins.
_asp = op('/project1/audio_spectrum')
if _asp is not None:
    try:
        _omp = _asp.par.outputmenu
        _fixed = next((o for o in _omp.menuNames if o != 'matchtofrequency'), None)
        if _fixed:
            _omp.val = _fixed
        _asp.par.outlength = 256
        _asp.par.fftsize = 2048
        _asp.cook(force=True)
        out['audio_spectrum_numSamples'] = _asp.numSamples
        out['audio_spectrum_cook_ms'] = round(_asp.cookTime, 3)
        # sanity: bands must still produce non-degenerate output
        _fb = op('/project1/fx_audio_bands')
        out['bands_after'] = {c.name: round(c.eval(), 4) for c in _fb.chans()} if _fb else None
    except Exception as e:
        out['audio_spectrum_err'] = str(e)

json.dump(out, open('/tmp/td_edit.json', 'w'), indent=2)

# Persist without the overwrite dialog: save to a FRESH path each run, then cp.
try:
    _p = '/Users/thomasadair/Desktop/_dj_look_out.toe'  # bash deletes this before run
    project.save(_p)
    print('[look_pass] SAVED %s' % _p)
    print('[look_pass] NOW RUN:  cp %s ~/Desktop/DJ_Graphics.3.toe' % _p)
except Exception as e:
    print('[look_pass] save failed: %s' % e)
print('[look_pass] done', out['after'])
