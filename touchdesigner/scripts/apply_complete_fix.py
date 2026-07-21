# apply_complete_fix.py -- ATOMIC, idempotent completion pass. Run once in the
# TD Textport after the tracker is running the seqlock writer:
#   exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/apply_complete_fix.py').read())
#
# Activates the seqlock body-mask reader (no-freeze WITH body outline), fixes the
# outline mirror, and verifies every prior fix is still in place. Writes a status
# JSON to /tmp/td_complete.json and saves to a FRESH .toe (then you cp -> LIVE).
import json

RSRC = '/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/segmentation_mask_reader.py'
out = {}

# --- 1. Install the SEQLOCK reader into the DAT + un-bypass body_mask_top ------
cb = op('/project1/segmentation_mask_reader')
cb.text = open(RSRC).read()                 # seqlock, non-blocking, no flush dependency
bmt = op('/project1/body_mask_top')
bmt.bypass = False
for _ in range(3):
    bmt.cook(force=True)
a = bmt.numpyArray()[..., :3]
out['reader'] = {
    'has_seqlock': ('_seq' in cb.text and 'djsam_bodymask_A' in cb.text),
    'bmt_bypass': bmt.bypass,
    'bmt_cook_ms': round(bmt.cookTime, 3),
    'bmt_out_max': [round(float(x), 3) for x in a.reshape(-1, 3).max(0)],
    'bmt_err': [str(x) for x in bmt.errors()],
}

# --- 2. Outline mirror fix (align outline to tracker's mirrored mask) ----------
of = op('/project1/outline_flip')
of.par.flipx = False
of.par.flipy = True
out['outline_flip'] = {'flipx': of.par.flipx.eval(), 'flipy': of.par.flipy.eval()}

# --- 3. Defensive: bound the outline blur cost (covers the GPU-cost hypothesis)-
og = op('/project1/outline_glow')
if og is not None:
    for pn in ('size', 'filterwidth', 'width'):
        if hasattr(og.par, pn):
            try:
                if og.par[pn].eval() > 20:
                    og.par[pn] = 20
            except Exception:
                pass
    out['outline_glow'] = {p.name: p.eval() for p in og.pars()
                           if p.name in ('size', 'filterwidth', 'width')}

# --- 4. Verify ALL prior work is intact (idempotent read-back) -----------------
asp = op('/project1/audio_spectrum')
pt = op('/project1/fx_palette_table')
pec = op('/project1/fx_palette_engine_cb')
mono = op('/project1/fx_palette_mono')
ke = op('/project1/fx_kick_env')
se = op('/project1/fx_snare_env')
w = op('/project1/perform')
d = op('/project1/perform_autostart')
out['preserved'] = {
    'audio_spectrum_out': asp.par.outlength.eval(), 'audio_spectrum_fft': asp.par.fftsize.eval(),
    'palette_rows': pt.numRows,
    'engine_linear': 'f = frac' in pec.text, 'engine_kick': '_kick_jump' in pec.text,
    'engine_snare': 'fx_snare_env' in pec.text,
    'mono_sat': mono.par.saturationmult.eval() if mono else None,
    'kick_release': ke.par.release.eval(), 'snare_release': se.par.release.eval(),
    'perform_monitor': w.par.monitor.eval(), 'perform_size': str(w.par.size.eval()),
    'dat_has_hisense': '_hisense' in d.text, 'performOnStart': project.performOnStart,
}
out['syphon'] = {'name': str(op('/project1/syphonOut1').par.sendername.eval()),
                 'active': op('/project1/syphonOut1').par.active.eval()}
out['perf_cook_ms'] = round(w.cookTime, 3)

json.dump(out, open('/tmp/td_complete.json', 'w'), indent=2, default=str)

# --- 5. Save to a FRESH path (no overwrite dialog); operator cp's to LIVE ------
try:
    import os
    p = '/Users/thomasadair/Desktop/_dj_complete.toe'
    if os.path.exists(p):
        os.remove(p)
    project.save(p)
    print('[complete] SAVED %s  ->  cp it onto ~/Desktop/DJ_Graphics_LIVE.toe' % p)
except Exception as e:
    print('[complete] save failed: %s (Cmd+S manually)' % e)
print('[complete] done:', json.dumps(out.get('reader')), '| perf', out['perf_cook_ms'], 'ms')
