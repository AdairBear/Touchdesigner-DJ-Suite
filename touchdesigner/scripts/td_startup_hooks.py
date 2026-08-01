# td_startup_hooks.py -- the ONE external file TD execs on every project load.
#
# Bootstrapped by a three-line loader in the perform_autostart Execute DAT (see
# BOOTSTRAP below). That loader is pasted and the .toe saved exactly ONCE; from
# then on every fix in this file takes effect on the next project load, with no
# further .toe saves and full git history.
#
# ===========================================================================
# WHY THIS FILE EXISTS
#
# Two fixes have now evaporated the same way: written to disk, never loaded by
# the running project.
#
#   segmentation_mask_reader.py  fixed on disk; the .toe kept its own baked-in
#                                copy (a black stub) until something manually
#                                reloaded it
#   audio_reactive_mapper        fixed on disk; the DAT lives INSIDE the .toe,
#                                so the per-frame freeze guard never ran
#
# The assumption that the mask reader "auto-loads from an external .py at
# startup" turned out to be false -- _reload_mask.py and
# aura_compositor._force_reload_mask_reader_once() both load from disk, but both
# are MANUALLY invoked. Nothing ran at project start. That is exactly why the
# black stub kept coming back: nothing auto-loaded the good version either.
#
# So there was no startup hook to hook into. This is that hook.
#
# ===========================================================================
# BOOTSTRAP -- do this ONCE, then never again
#
# In TD: open the perform_autostart Execute DAT and add these three lines to
# onStart (it already fires at project start). Then File > Save (Cmd+S).
#
#     try:
#         exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/td_startup_hooks.py').read())
#     except Exception as _e:
#         print('[startup-hooks] FAILED:', _e)
#
# The try/except matters: if this file is ever missing or broken, the project
# must still open. A startup hook that can prevent the show from loading is
# worse than the bugs it fixes.
#
# Rollback: archive/toe/DJ_Graphics_LIVE.2026-08-01.toe is a byte-identical
# snapshot taken before this change (sha 12be8126c5ade243f19129c6a67d9dbb227c5499).
#
# ===========================================================================
# DESIGN RULES
#
#   1. NEVER RAISE. Every hook is wrapped. A failure here must degrade to a
#      printed line, never a project that will not open.
#   2. RUN ONCE PER LOAD. perform_autostart fires on Start AND FrameStart, so
#      an unguarded hook would re-scan the whole node tree every frame -- which
#      would itself be a performance bug of the kind we are here to fix.
#   3. IDEMPOTENT. Safe to exec by hand at any time to re-apply.
#   4. REPORT. Writes /tmp/td_startup_hooks.json so the agent (and a human) can
#      see what ran without opening TD.
# ===========================================================================

import json
import time

_REPORT = "/tmp/td_startup_hooks.json"
_MARKER = "td_startup_hooks_ran"

_report = {"ts": time.time(), "hooks": {}}


def _log(name, status, detail=""):
    _report["hooks"][name] = {"status": status, "detail": str(detail)[:300]}
    print("[startup-hooks] %-22s %-8s %s" % (name, status, str(detail)[:120]))


# --- Rule 2: once per project load -----------------------------------------
def _already_ran():
    try:
        root = op("/project1")
        if root is None:
            return False
        if root.fetch(_MARKER, None) is not None:
            return True
        root.store(_MARKER, time.time())
        return False
    except Exception:
        return False


# --- Hook 1: the audio-reactive per-frame guard ----------------------------
_GUARD = """

# ---- FREEZE GUARD (td_startup_hooks.py) -----------------------------------
# A CHOP Execute DAT fires onValueChange once per changed SAMPLE. audio_spectrum
# has hundreds of bins, so under music the full handler ran hundreds of times
# per frame, each call recomputing the same band energies and rewriting the same
# parameters. Run the real handler ONCE PER FRAME instead.
#
# Reactivity is UNCHANGED: 60 updates/sec is the rate the graphics are drawn at.
# Reacting more often than the screen refreshes produces no visible motion, only
# work. Nothing is smoothed, damped, decimated or throttled.
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


def _install_audio_guard():
    """Find the audio-reactive callback DAT BY BEHAVIOUR and guard it.

    By behaviour, not by name: the hardcoded /project1/audio_reactive_mapper
    did not exist ("not found" on the live rig) even though the graphics
    visibly react to audio. Any DAT defining onValueChange is a CHOP Execute
    callback; any of those referencing a spectrum/audio CHOP is a candidate for
    the per-sample storm.
    """
    targets, skipped = [], []
    for o in op("/").findChildren(type=DAT, depth=99):
        try:
            text = o.text or ""
        except Exception:
            continue
        if "def onValueChange" not in text:
            continue
        if not any(k in text.lower() for k in ("spectrum", "audio", "band", "fft")):
            continue
        if "_freeze_guard_installed" in text:
            skipped.append(o.path)
            continue
        try:
            o.text = text + _GUARD
            targets.append(o.path)
        except Exception as e:
            _log("audio_guard", "ERROR", "%s: %s" % (o.path, e))

    if targets:
        _log("audio_guard", "INSTALLED", ", ".join(targets))
    elif skipped:
        _log("audio_guard", "ok", "already guarded: " + ", ".join(skipped))
    else:
        # A real finding, not a non-event: if nothing defines onValueChange,
        # the audio reactivity is not CHOP-Execute-driven and the per-sample
        # storm theory is dead.
        _log("audio_guard", "NONE-FOUND", "no DAT defines onValueChange")
    _report["audio_targets"] = targets
    _report["audio_already_guarded"] = skipped


# --- Hook 2: report the mask reader's state (does not modify it) -----------
def _report_mask_reader():
    d = op("/project1/segmentation_mask_reader")
    if d is None:
        _log("mask_reader", "MISSING", "/project1/segmentation_mask_reader")
        return
    text = d.text or ""
    is_stub = "np.zeros((480,640,4)" in text and "djsam_bodymask_A" not in text
    _log(
        "mask_reader",
        "STUB" if is_stub else "ok",
        "black stub -- run _reload_mask.py" if is_stub else "seqlock reader",
    )
    _report["mask_reader_is_stub"] = is_stub


# --- Runner -----------------------------------------------------------------
def _run():
    if _already_ran():
        return
    print("[startup-hooks] running (project load)")
    for name, fn in (
        ("audio_guard", _install_audio_guard),
        ("mask_reader", _report_mask_reader),
    ):
        try:
            fn()
        except Exception as e:  # Rule 1: never raise
            _log(name, "ERROR", e)
    try:
        json.dump(_report, open(_REPORT, "w"), indent=2, default=str)
        print("[startup-hooks] report -> " + _REPORT)
    except Exception:
        pass


try:
    _run()
except Exception as _e:  # Rule 1, outermost
    print("[startup-hooks] FATAL (project load continues):", _e)
