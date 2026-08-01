# install_audio_mapper_fix.py -- put the freeze fix into the RUNNING project.
#
#   exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/install_audio_mapper_fix.py').read())
#
# ===========================================================================
# WHY THIS EXISTS
#
# The freeze fix was written to audio_reactive_mapper.py on disk. It never ran.
#
#   DJ_Graphics_LIVE.toe last saved   Jul 19 01:48
#   freeze fix committed              Jul 31 22:48   (12 days later)
#   anything that reloads the mapper  nothing -- _reload_mask.py covers only
#                                     segmentation_mask_reader + aura_compositor
#
# audio_reactive_mapper is a CHOP Execute DAT living INSIDE the .toe. Loading
# the project loads the Jul 19 copy. This is the same trap as the mask-reader
# bug: code fixed on disk is not code in the running system.
#
# ===========================================================================
# WHAT IT DOES -- AND WHAT IT DELIBERATELY DOES NOT
#
# It does NOT replace the DAT's text with the on-disk file. That would:
#   * discard any edits baked into the .toe that never made it to disk, and
#   * re-run _bootstrap_audio_chain() at import, which rewrites audio_in's
#     driver/device parameters -- an intrusive thing to do mid-session.
#
# Instead it APPENDS a wrapper that decorates the existing onValueChange:
#
#     _orig = onValueChange
#     def onValueChange(...):
#         if this frame already handled: return
#         return _orig(...)
#
# The original band-energy, smoothing, onset and parameter-mapping code is
# untouched and still does exactly what it did. Only the CALL RATE changes.
#
# ===========================================================================
# THIS PRESERVES THE REACTIVITY. That is the point, not a caveat.
#
# The feature is the pulse -- graphics reacting to the music. The bug was never
# that the mapper reacted; it is that a CHOP Execute DAT fires onValueChange
# once per changed SAMPLE, and audio_spectrum has hundreds of bins, so under
# music the full mapping ran hundreds of times per frame. Every one of those
# calls read the same spectrum and wrote the same parameters.
#
# After the wrapper it runs ONCE PER FRAME -- 60 times a second. The graphics
# are drawn 60 times a second. Reacting more often than the screen refreshes
# produces no additional visible motion; it only produces work. So:
#
#     reactivity  = unchanged (every frame, full band/onset/burst response)
#     work        = ~1/300th
#
# Nothing is smoothed, damped, decimated, or throttled. If the pulse looks
# different afterwards, that is a bug in this wrapper, not the intent.
# ===========================================================================

_WRAP = """

# ---- FREEZE GUARD (install_audio_mapper_fix.py, 2026-08-01) ----------------
# A CHOP Execute DAT fires onValueChange once per changed SAMPLE. audio_spectrum
# has hundreds of bins, so under music this ran hundreds of times per frame,
# each call redoing the same band energies and the same parameter writes.
# Run the real handler once per frame instead. Full reactivity, ~1/300th work.
try:
    _freeze_guard_installed
except NameError:
    _freeze_guard_installed = True
    _fg_last_frame = -1
    _fg_calls = 0        # callbacks TD delivered
    _fg_runs = 0         # times the real handler actually ran
    _fg_orig_onValueChange = onValueChange

    def onValueChange(channel, sampleIndex, val, prev):
        global _fg_last_frame, _fg_calls, _fg_runs
        _fg_calls += 1
        try:
            f = absTime.frame
        except Exception:
            f = -1
        if f == _fg_last_frame and f != -1:
            return
        _fg_last_frame = f
        _fg_runs += 1
        return _fg_orig_onValueChange(channel, sampleIndex, val, prev)
# ---------------------------------------------------------------------------
"""

import json

out = {}
d = op("/project1/audio_reactive_mapper")

if d is None:
    print("[mapper-fix] FAIL: /project1/audio_reactive_mapper not found")
else:
    txt = d.text or ""
    out["dat"] = d.path
    out["text_len_before"] = len(txt)
    out["already_fixed_ondisk_style"] = "_last_processed_frame" in txt
    out["already_wrapped"] = "_freeze_guard_installed" in txt

    sp = op("/project1/audio_spectrum")
    if sp is not None:
        out["spectrum_numSamples"] = sp.numSamples
        out["spectrum_numChans"] = sp.numChans
        # This is the multiplier: callbacks per frame before the fix.
        print(
            "[mapper-fix] audio_spectrum has %d samples x %d chan(s)"
            % (sp.numSamples, sp.numChans)
        )
        print("[mapper-fix] -> that many onValueChange calls PER FRAME under music")

    if out["already_wrapped"]:
        print("[mapper-fix] already installed -- nothing to do (idempotent)")
    elif out["already_fixed_ondisk_style"]:
        print("[mapper-fix] this DAT already carries the on-disk per-frame guard")
    else:
        d.text = txt + _WRAP
        out["text_len_after"] = len(d.text)
        out["installed"] = True
        print(
            "[mapper-fix] INSTALLED the per-frame guard (wrapper, original code untouched)"
        )

    # Counters, if the wrapper has been running.
    try:
        mod = d.module
        calls = getattr(mod, "_fg_calls", None)
        runs = getattr(mod, "_fg_runs", None)
        if calls:
            out["calls"] = calls
            out["runs"] = runs
            out["ratio"] = round(calls / max(runs, 1), 1)
            print(
                "[mapper-fix] LIVE COUNTERS: %d callbacks delivered, %d handler runs "
                "(%.0fx reduction)" % (calls, runs, calls / max(runs, 1))
            )
    except Exception as e:
        out["counter_err"] = str(e)

    json.dump(out, open("/tmp/td_mapper_fix.json", "w"), indent=2, default=str)

print("[mapper-fix] " + "-" * 58)
print("[mapper-fix] NOW PROVE IT, with music playing:")
print("[mapper-fix]   1. start a track")
print("[mapper-fix]   2. watch the graphics -- they must PULSE and not freeze")
print("[mapper-fix]   3. re-run this script: the LIVE COUNTERS line prints the")
print("[mapper-fix]      real callback:run ratio measured on your rig.")
print("[mapper-fix]      Expect roughly (spectrum samples) : 1.")
print("[mapper-fix] ")
print("[mapper-fix] IF THE GRAPHICS STILL FREEZE with the wrapper installed and")
print("[mapper-fix] the ratio is large, the mapper was NOT the bottleneck --")
print("[mapper-fix] say so and we look at the other CHOP Execute DATs and the")
print("[mapper-fix] BUTT/OBS encoder load. Do not assume this fixed it.")
print("[mapper-fix] ")
print("[mapper-fix] TO MAKE IT SURVIVE A RELOAD: File > Save (Cmd+S) -- this")
print("[mapper-fix] overwrites DJ_Graphics_LIVE.toe in place. Do NOT Save As.")
print("[mapper-fix] " + "-" * 58)
