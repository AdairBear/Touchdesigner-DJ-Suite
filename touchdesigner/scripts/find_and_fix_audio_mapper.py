# find_and_fix_audio_mapper.py -- locate the audio-reactive DAT ANYWHERE in the
# project, then install the per-frame freeze guard into it.
#
#   exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/find_and_fix_audio_mapper.py').read())
#
# ===========================================================================
# WHY THIS REPLACES install_audio_mapper_fix.py
#
# That script hardcoded /project1/audio_reactive_mapper and reported
# "not found". The node exists -- the graphics visibly react to audio -- so the
# PATH was wrong, not the node. Hardcoding a path I had never read from the live
# project was the mistake; this searches for it instead.
#
# Search is by BEHAVIOUR, not by name: any DAT whose text defines onValueChange
# is a CHOP Execute callback, and any of those referencing a spectrum/audio CHOP
# is a candidate for the per-sample storm. That finds the node whatever it is
# called and wherever it is nested.
#
# SET DRY_RUN = True to only LIST what it finds and change nothing. Do that
# first if you want to see the candidates before anything is written.
# ===========================================================================

DRY_RUN = False

_WRAP = """

# ---- FREEZE GUARD (find_and_fix_audio_mapper.py, 2026-08-01) --------------
# A CHOP Execute DAT fires onValueChange once per changed SAMPLE. An audio
# spectrum CHOP has hundreds of bins, so under music the full handler ran
# hundreds of times per frame, each call redoing the same band energies and the
# same parameter writes. Run the real handler once per frame instead.
# Reactivity is UNCHANGED -- 60 updates/sec is the rate the graphics are drawn
# at. Nothing is smoothed, damped or decimated.
try:
    _freeze_guard_installed
except NameError:
    _freeze_guard_installed = True
    _fg_last_frame = -1
    _fg_calls = 0
    _fg_runs = 0
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

report = {"candidates": [], "installed": [], "already": [], "dry_run": DRY_RUN}

# --- 1. FIND every CHOP Execute-style callback DAT in the whole project -----
found = []
try:
    for o in op("/").findChildren(type=DAT, depth=99):
        try:
            t = o.text or ""
        except Exception:
            continue
        if "def onValueChange" not in t:
            continue
        audio_ish = any(
            k in t.lower() for k in ("spectrum", "audio", "bass", "band", "fft")
        )
        entry = {
            "path": o.path,
            "type": o.type,
            "chars": len(t),
            "audio_related": audio_ish,
            "already_guarded": "_freeze_guard_installed" in t,
            "has_ondisk_guard": "_last_processed_frame" in t,
        }
        # What CHOP is it watching, and is per-value firing even enabled?
        for pname in ("chop", "valuechange", "active"):
            p = getattr(o.par, pname, None)
            if p is not None:
                try:
                    entry[pname] = p.eval()
                except Exception:
                    pass
        found.append((o, entry))
        report["candidates"].append(entry)
except Exception as e:
    report["search_error"] = str(e)

print("[find-mapper] ===== CALLBACK DATs FOUND =====")
if not found:
    print("[find-mapper] NONE. No DAT in the project defines onValueChange.")
    print("[find-mapper] The audio reactivity is therefore NOT driven by a CHOP")
    print("[find-mapper] Execute DAT -- so the per-sample storm theory is DEAD,")
    print("[find-mapper] and the freeze is elsewhere. That is a real result.")
for _o, e in found:
    print(
        "[find-mapper] %-45s audio=%s watching=%s valuechange=%s active=%s guarded=%s"
        % (
            e["path"],
            e["audio_related"],
            e.get("chop"),
            e.get("valuechange"),
            e.get("active"),
            e["already_guarded"],
        )
    )

# --- 2. Report the multiplier: how many samples fire per frame --------------
for name in ("audio_spectrum", "spectrum", "audio_analysis"):
    sp = op("/project1/" + name)
    if sp is not None:
        try:
            print(
                "[find-mapper] %s: %d samples x %d chan -> that many callbacks PER FRAME"
                % (sp.path, sp.numSamples, sp.numChans)
            )
            report["spectrum"] = {
                "path": sp.path,
                "numSamples": sp.numSamples,
                "numChans": sp.numChans,
            }
        except Exception:
            pass
        break

# --- 3. INSTALL the guard into the audio-related ones -----------------------
targets = [(o, e) for o, e in found if e["audio_related"]]
if DRY_RUN:
    print(
        "[find-mapper] DRY_RUN -- nothing written. %d target(s) would be patched."
        % len(targets)
    )
else:
    for o, e in targets:
        if e["already_guarded"] or e["has_ondisk_guard"]:
            report["already"].append(e["path"])
            print("[find-mapper] already guarded: %s" % e["path"])
            continue
        try:
            o.text = (o.text or "") + _WRAP
            report["installed"].append(e["path"])
            print("[find-mapper] INSTALLED guard -> %s" % e["path"])
        except Exception as ex:
            print("[find-mapper] FAILED on %s: %s" % (e["path"], ex))

# --- 4. Live counters, if the guard has been running ------------------------
for o, e in found:
    try:
        mod = o.module
        calls = getattr(mod, "_fg_calls", 0)
        runs = getattr(mod, "_fg_runs", 0)
        if calls:
            print(
                "[find-mapper] COUNTERS %s: %d callbacks, %d handler runs (%.0fx)"
                % (e["path"], calls, runs, calls / max(runs, 1))
            )
            report.setdefault("counters", {})[e["path"]] = {
                "calls": calls,
                "runs": runs,
            }
    except Exception:
        pass

try:
    json.dump(report, open("/tmp/td_find_mapper.json", "w"), indent=2, default=str)
    print("[find-mapper] report -> /tmp/td_find_mapper.json")
except Exception:
    pass

print("[find-mapper] " + "-" * 58)
print("[find-mapper] NOW: play a track. If the graphics still freeze, re-run")
print("[find-mapper] this line -- the COUNTERS show the real callback:run ratio.")
print("[find-mapper] A large ratio + still frozen = the mapper was NOT the cause.")
print("[find-mapper] Cmd+S to keep it across a reload.")
print("[find-mapper] " + "-" * 58)
