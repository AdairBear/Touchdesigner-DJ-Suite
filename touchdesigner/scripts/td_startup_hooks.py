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
import os
import sys
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


# --- CPU/GPU load reduction (2026-08-01, Cowork) ---------------------------
# OBS delivers 30 fps, so cooking at 60 doubles TD + WindowServer work for
# frames nobody sees. Realtime On makes TD drop frames under load instead of
# lagging the whole cook. Reversible: delete this function + its tuple entry.
def _reduce_render_load():
    try:
        before = (project.cookRate, project.realTime)
        project.cookRate = 30
        project.realTime = True
        _log("render_load", "OK", "cookRate->30 realTime->True (was %s)" % (before,))
    except Exception as e:
        _log("render_load", "ERROR", e)


# --- Audio-in device -> reactivity source (2026-08-01, Cowork) -------------
# ROOT-CAUSE FIX (proven live): TD's audio_in reading the PreSonus 1824c -- the
# device Serato drives -- stalled the render on music-start. We now point audio_in
# at "Serato Virtual Audio" (Serato's "Make Audio Available to Other Applications"
# virtual device): non-contended AND it carries the real master, so beat-reactivity
# works. Falls back to BlackHole (safe but silent), then leaves the default.
# aura_compositor also force-sets this device on load; we set it here AND re-assert
# ~4s later so we win that race. Reversible: delete this function + its tuple entry
# (prior working value before this change was BlackHole2ch_UID).
def _audio_in_reactive_source():
    ai = op("/project1/audio_in")
    if ai is None:
        _log("audio_in_src", "MISSING", "/project1/audio_in")
        return
    try:
        names = list(ai.par.device.menuNames or [])
        labels = list(ai.par.device.menuLabels or [])

        def _pick(kw):
            for lab, nm in zip(labels, names):
                if kw in (lab or "").lower() or kw in (nm or "").lower():
                    return nm
            return None

        # 2026-08-01: with the outline_glow blur CLAMPED (size capped ~52px) real audio
        # no longer freezes the cook, so target Serato Virtual Audio (carries the master
        # -> reactivity works). BlackHole is the safe silent fallback if it's absent.
        dev = _pick("serato virtual") or _pick("serato") or _pick("blackhole")
        if dev is None:
            _log("audio_in_src", "NO-DEVICE", "left %r" % ai.par.device.eval())
            return
        ai.par.device = dev
        # Re-assert after aura_compositor's on-load device force (~4s @30fps).
        run("op('/project1/audio_in').par.device = %r" % dev, delayFrames=120)
        _log("audio_in_src", "OK", "device -> %s (+re-assert @120f)" % dev)
    except Exception as e:
        _log("audio_in_src", "ERROR", e)


# --- Audio-reactive glow: kick/snare transient drive (2026-08-02, Cowork) --
# Drives outline_glow.size from the KICK+SNARE trigger envelopes (0-1) so it punches
# on drums instead of swelling with sustained bass. The min(...,40) clamp is part of
# the expression, so the blur can NEVER explode (that is the freeze fix). audio_amp
# gain is kept at 100 for a musical range. Applied on every load so it survives a
# relaunch even without a project.save(). Reversible: delete this function + its
# tuple entry (outline_glow then reverts to whatever is baked in the .toe).
def _apply_glow_transient():
    try:
        amp = op("/project1/audio_amp")
        if amp is not None:
            amp.par.gain = 100.0
        og = op("/project1/outline_glow")
        if og is None:
            _log("glow_transient", "MISSING", "/project1/outline_glow")
            return
        og.par.size.expr = (
            "12 + min(op('fx_kick_env')['bass']*40 + "
            "op('fx_snare_env')['high']*15, 40)"
        )
        _log("glow_transient", "OK", "size -> kick/snare punch (clamped 40)")
    except Exception as e:
        _log("glow_transient", "ERROR", e)


# --- RAVE look pass (2026-08-02, Cowork) -----------------------------------
# Thomas's post-show notes: reactivity must be MUCH bigger/unmistakable, remove
# BROWN (the old CYAN->ORANGE->PURPLE palette's orange muddied to brown), go neon/
# UV rave, reduce trails ~10-15%, and make it evolve. Modelled on the proven
# apply_look_pass.py structure. Every step is isolated in its own try/except so a
# wrong param name can never break the show. Blur clamp is left untouched
# (glow_transient owns outline_glow.size -> freeze-safe). Reversible: delete this
# function + its tuple entry, then re-run apply_look_pass.py for the old look.
_RAVE_ENGINE = (
    "# fx_palette_engine -- RAVE/UV neon sweep. KICK = jump to next anchor.\n"
    "# SNARE = big brightness POP (up to +250%).\n"
    "_kick_jump = 0\n"
    "_kick_prev = 0.0\n"
    "def onCook(scriptOp):\n"
    "    global _kick_jump, _kick_prev\n"
    "    scriptOp.clear()\n"
    "    tbl = op('fx_palette_table')\n"
    "    names = ('primaryR','primaryG','primaryB','secondaryR','secondaryG','secondaryB')\n"
    "    if tbl is None or tbl.numRows == 0:\n"
    "        for nm in names:\n"
    "            scriptOp.appendChan(nm).vals = [1.0]\n"
    "        return\n"
    "    n = tbl.numRows\n"
    "    ke = op('fx_kick_env')\n"
    "    kv = 0.0\n"
    "    if ke is not None and ke.numChans > 0:\n"
    "        try:\n"
    "            kv = ke['bass'].eval()\n"
    "        except Exception:\n"
    "            kv = ke[0].eval()\n"
    "    if kv > 0.5 and _kick_prev <= 0.5:\n"
    "        _kick_jump += 1\n"
    "    _kick_prev = kv\n"
    "    se = op('fx_snare_env')\n"
    "    sv = 0.0\n"
    "    if se is not None and se.numChans > 0:\n"
    "        try:\n"
    "            sv = se['high'].eval()\n"
    "        except Exception:\n"
    "            sv = se[0].eval()\n"
    "    bright = 1.0 + sv * 2.5\n"
    "    period = 22.0\n"
    "    pos = (absTime.seconds / period) + _kick_jump\n"
    "    idx = int(pos) % n\n"
    "    nxt = (idx + 1) % n\n"
    "    f = pos - int(pos)\n"
    "    def cell(r, c):\n"
    "        try:\n"
    "            return float(tbl[r, c].val)\n"
    "        except Exception:\n"
    "            return 0.0\n"
    "    for col, nm in enumerate(names):\n"
    "        a = cell(idx, col)\n"
    "        b = cell(nxt, col)\n"
    "        scriptOp.appendChan(nm).vals = [(a + (b - a) * f) * bright]\n"
    "    return\n"
)


def _apply_rave_look():
    def _step(name, fn):
        try:
            fn()
            _log("rave:" + name, "OK", "")
        except Exception as e:
            _log("rave:" + name, "ERR", e)

    # 1) NEON/UV palette (no orange -> no brown). 5 anchors, each row = this + next.
    def _palette():
        tbl = op("/project1/fx_palette_table")
        CY = (0.0, 1.0, 1.0)      # electric cyan
        MG = (1.0, 0.0, 1.0)      # UV magenta
        GR = (0.35, 1.0, 0.06)    # acid green
        PK = (1.0, 0.06, 0.55)    # hot pink
        VT = (0.6, 0.0, 1.0)      # electric violet
        rows = [CY + MG, MG + GR, GR + PK, PK + VT, VT + CY]
        tbl.clear()
        for row in rows:
            tbl.appendRow(["%.4f" % v for v in row])
    _step("palette", _palette)

    # 2) engine: bigger snare pop + faster sweep (more variation over time)
    def _engine():
        cb = op("/project1/fx_palette_engine_cb")
        cb.text = _RAVE_ENGINE
        pe = op("/project1/fx_palette_engine")
        if pe is not None:
            pe.cook(force=True)
    _step("engine", _engine)

    # 3) purer neon: desaturate the base more before the palette multiply
    def _mono():
        m = op("/project1/fx_palette_mono")
        if m is not None and hasattr(m.par, "saturationmult"):
            m.par.saturationmult = 0.12
    _step("mono", _mono)

    # 4) BIG brightness pulse on the outline itself on every kick
    def _outline_bright():
        op("/project1/outline_level").par.brightness1.expr = (
            "2.5 + op('fx_kick_env')['bass'] * 6"
        )
    _step("outline_bright", _outline_bright)

    # 5) bigger kick flash layer
    def _kick_bright():
        op("/project1/fx_kick_bright").par.brightness1.expr = (
            "1 + op('fx_kick_env')['bass'] * 8"
        )
    _step("kick_bright", _kick_bright)

    # 6) zoom/scale punch on kick (guarded: transformTOP param name varies)
    def _zoom():
        ex = op("/project1/fx_kick_expand")
        expr = "1 + op('fx_kick_env')['bass'] * 0.25"
        done = False
        for a, b in (("sx", "sy"), ("scalex", "scaley")):
            if hasattr(ex.par, a) and hasattr(ex.par, b):
                getattr(ex.par, a).expr = expr
                getattr(ex.par, b).expr = expr
                done = True
                break
        if not done and hasattr(ex.par, "scale"):
            ex.par.scale.expr = expr
    _step("zoom", _zoom)

    # 7) UV fire aura (kill the orange tint that browned the mix)
    def _fire():
        ft = op("/project1/fire_tint")
        ft.par.colorr = 1.0
        ft.par.colorg = 0.1
        ft.par.colorb = 0.9
    _step("fire_uv", _fire)

    # 8) trails reduced ~10-15% (0.92 -> 0.89 persistence base)
    def _trails():
        op("/project1/fx_trail_hsv").par.valuemult.expr = (
            "0.890000 - op('fx_lfo_decay')['chan1'] * 0.03"
        )
    _step("trails", _trails)

    # 9) auto-cycle visual mode (fire/lightning) every 30s -> evolving variation
    def _modes():
        vs = op("/project1/visual_switch")
        vs.par.index.expr = "int(absTime.seconds / 30.0) % 2"
    _step("modes", _modes)


# --- Per-profile .toe boot (2026-08-05) -------------------------------------
# Lets five COPIES of this .toe boot into five different looks while sharing
# this one external hook: the look is read from the project FILENAME. A copy
# named dj_launcher_STROBE_ACID.toe boots STROBE_ACID; nothing else differs
# between the copies, so there is no divergence to maintain.
#
# NO-OP FOR THE LIVE SHOW FILE. The canonical file is DJ_Graphics_LIVE.toe,
# which does not carry the dj_launcher_ prefix, so profile_from_toe_name()
# returns None and this function returns before touching anything. The show
# file keeps booting to UV_RAVE via _apply_rave_look() exactly as before. That
# property is asserted directly in tests/test_dj_profile_toes.py rather than
# argued for here.
#
# Runs AFTER rave_look in the tuple below so a profile wins over the base look.
# Reversible: delete this function and its tuple entry.
_PROFILE_SCRIPTS_DIR = "/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts"


def _current_toe_name():
    """Best-effort filename of the running project, or '' if undiscoverable."""
    try:
        name = project.name
        if name:
            return str(name)
    except Exception:
        pass
    try:
        return os.path.basename(str(project.saveFile))
    except Exception:
        return ""


def _apply_profile_for_this_toe():
    """Apply the graphics profile this .toe's filename encodes, if any."""
    name = _current_toe_name()
    if not name:
        _log("graphics_profile", "skip", "could not determine project filename")
        return
    try:
        if _PROFILE_SCRIPTS_DIR not in sys.path:
            sys.path.insert(0, _PROFILE_SCRIPTS_DIR)
        import dj_graphics_profiles as _gp
    except Exception as e:
        _log("graphics_profile", "ERROR", "import failed: %s" % e)
        return

    profile = _gp.profile_from_toe_name(name)
    if profile is None:
        # The canonical show file lands here. Nothing is applied, by design.
        _log("graphics_profile", "skip", "%s is not a profile .toe" % name)
        _report["graphics_profile"] = None
        return

    result = _gp.apply_profile(profile)
    _log("graphics_profile", "OK" if result.get("applied") else "FAILED",
         "%s (from filename %s)" % (profile, name))
    _report["graphics_profile"] = profile


# --- Runner -----------------------------------------------------------------
def _run():
    if _already_ran():
        return
    print("[startup-hooks] running (project load)")
    for name, fn in (
        ("render_load", _reduce_render_load),
        ("audio_in_src", _audio_in_reactive_source),
        ("glow_transient", _apply_glow_transient),
        ("rave_look", _apply_rave_look),
        # AFTER rave_look so a per-profile .toe overrides the base look.
        # No-op unless the filename carries the dj_launcher_ prefix.
        ("graphics_profile", _apply_profile_for_this_toe),
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
