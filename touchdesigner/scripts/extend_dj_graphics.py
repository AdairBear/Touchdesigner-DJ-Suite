# extend_dj_graphics.py — Extended reactive-effects layer for DJ_Graphics
# =====================================================================
# WHAT THIS IS
#   A single, paste-into-Textport script that bolts four extended-effects
#   stages onto the EXISTING, hand-built DJ_Graphics outline chain without
#   touching the .toe on disk. It is idempotent: re-running reuses nodes and
#   only re-asserts wiring, so you can paste it as many times as you like.
#
#   The four stages (in signal order):
#       1. PALETTE   — 4-palette rotation w/ 3 s crossfade  (recolor)
#       2. TRAILS    — Feedback TOP motion trails, colour-drifting decay
#       3. KICK      — bass-triggered radial flash from body centre
#       4. SNARE     — high-freq-triggered shake / RGB split
#   plus an EVOLUTION layer (LFO + noise + 30 s energy accumulator) that
#   slowly drifts the trail/kick/snare parameters so the loop never sits still.
#
# HOW TO USE  (Phase 2 — at your desk, TD open, tracker + audio running)
#   1. Textport:  Alt+T
#   2. Confirm P_PATH / SRC / SYPHON below match your network (defaults are the
#      standard /project1 chain).  Confirm REPO_ROOT if you enable GLSL split.
#   3. Paste this whole file, press Enter.
#   4. Watch the log. Every node prints as it is created/reused, and a preflight
#      block reports PASS/FAIL for the nodes it needs to find.
#   5. If trails don't appear, see TRAIL_COMPOSITE note below.
#   To REMOVE everything this added:  extend_dj_graphics_teardown()  (defined
#   at the bottom) — it rewires syphonOut1 back to SRC and deletes fx_* nodes.
#
# ---------------------------------------------------------------------
# THE FEEDBACK TOP GOTCHA  ("Not enough sources specified")
#   That error is thrown by the *Composite TOP*, not the Feedback TOP: it fires
#   the instant the Composite cooks with fewer than 2 connected inputs. Last
#   night's failure was setting feedback.par.top while the Composite still had
#   one input open. The bullet-proof order (used below) is:
#       a. create feedback + composite + decay nodes
#       b. wire BOTH composite inputs first  (source -> in0, decay -> in1)
#       c. wire the feedback's own input (initialiser)
#       d. ONLY THEN set feedback.par.top = composite
#   We also use operand "maximum" instead of the doc-standard "over": maximum is
#   commutative (input order can't be wrong) and needs no alpha channel, so a
#   silhouette drawn on opaque black still trails. If you'd rather use the
#   classic look, set TRAIL_COMPOSITE = "over" (needs source alpha) or "add".
# =====================================================================

import os

# ---------------------------------------------------------------------
# CONFIG — edit only if your network differs from the standard build
# ---------------------------------------------------------------------
REPO_ROOT = "/Users/thomasadair/projects/touchdesigner-dj-suite"

P_PATH = "/project1"          # COMP the DJ_Graphics chain lives in
SRC = "final_composite"       # silhouette source (the Null feeding syphon)
SYPHON = "syphonOut1"         # Syphon Spout Out TOP to re-route through the FX
AUDIO_SPECTRUM = "audio_spectrum"  # Audio Spectrum CHOP (bass/high tap)
AUDIO_AMP = "audio_amp"       # Math CHOP fallback if spectrum is absent

OUT_W, OUT_H = 1280, 720      # must match outline_fit / final output

# --- Trails -----------------------------------------------------------
TRAIL_DECAY = 0.92            # per-frame value multiply (0.89-0.95 typical)
TRAIL_HUE_DRIFT = 0.004       # per-frame hue rotate on the trail (0-1 == 0-360)
TRAIL_SAT = 1.0              # trail saturation multiply
TRAIL_COMPOSITE = "maximum"   # maximum|over|add|screen  (see gotcha note above)

# --- Kick flash -------------------------------------------------------
KICK_THRESH = 0.35            # bass energy trigger threshold
KICK_ATTACK = 0.005           # s
KICK_RELEASE = 0.20           # s  (~200 ms flash)
KICK_INTENSITY = 0.35         # max extra radial scale at full flash

# --- Snare shake ------------------------------------------------------
SNARE_THRESH = 0.30           # high-freq trigger threshold
SNARE_ATTACK = 0.003          # s
SNARE_RELEASE = 0.15          # s  (~150 ms shake)
SNARE_SHAKE_PX = 8.0          # max displacement in pixels (3-8 recommended)
USE_GLSL_RGB_SPLIT = False    # False = transform jitter (bullet-proof, no compile)
                              # True  = inline-GLSL chromatic-aberration split

# --- Evolution --------------------------------------------------------
LFO_HUE_HZ = 0.005            # very slow colour drift   (~200 s period)
LFO_GLOW_HZ = 0.01            # glow baseline drift       (~100 s period)
LFO_DECAY_HZ = 0.02           # trail-decay drift         (~50 s period)
EVO_WINDOW_S = 30.0           # beat-density accumulator window
EVO_MIN, EVO_MAX = 0.6, 1.5   # master-intensity range the accumulator maps to

# --- Palette rotation -------------------------------------------------
PALETTE_PERIOD_S = 240.0      # swap every 4 minutes
PALETTE_XFADE_S = 3.0         # 3 s crossfade between palettes
# primaryRGB, secondaryRGB per palette (0-1 floats)
PALETTES = [
    # cyan / hot-pink
    (0.0, 1.0, 1.0,   1.0, 0.08, 0.55),
    # fire-orange / gold
    (1.0, 0.42, 0.0,  1.0, 0.82, 0.15),
    # violet / blue
    (0.6, 0.2, 1.0,   0.15, 0.35, 1.0),
    # acid-green / near-black
    (0.5, 1.0, 0.05,  0.03, 0.06, 0.02),
]

# Layout origin for the new FX nodes (kept clear of the existing chain).
X0, Y0, DX, DY = 0, -500, 220, -140


# ---------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------
def _log(msg):
    print("[extend_dj] " + msg)


def _resolve_parent():
    """Find the COMP that holds the DJ_Graphics chain. Prefer P_PATH; fall back
    to scanning every COMP for one that already contains SRC or SYPHON."""
    p = op(P_PATH)
    if p is not None and (p.op(SRC) is not None or p.op(SYPHON) is not None):
        return p
    # scan
    for comp in root.findChildren(type=COMP, maxDepth=3):
        try:
            if comp.op(SRC) is not None or comp.op(SYPHON) is not None:
                _log("parent auto-detected: " + comp.path)
                return comp
        except Exception:
            pass
    return p  # may be None; preflight will report it


P = _resolve_parent()


def _op(kind, name, col=0, row=0):
    """Create (or reuse) `name` under P, laid out on a clear grid."""
    if P is None:
        raise RuntimeError("parent COMP not found — cannot create " + name)
    ex = P.op(name)
    if ex is not None:
        _log("reuse  " + name + " (" + ex.type + ")")
        node = ex
    else:
        node = P.create(kind, name)
        _log("create " + name + " (" + node.type + ")")
    node.nodeX = X0 + col * DX
    node.nodeY = Y0 + row * DY
    return node


def _setpar(node, name, value):
    """Set a parameter iff it exists on this build; log and continue if not."""
    if hasattr(node.par, name):
        try:
            setattr(getattr(node.par, name), "val", value)
            return True
        except Exception as e:
            _log("  par warn " + node.name + "." + name + " = " + repr(value) + " : " + str(e))
    return False


def _setexpr(node, name, expr):
    """Bind a parameter to an expression iff the parameter exists."""
    if hasattr(node.par, name):
        try:
            getattr(node.par, name).expr = expr
            return True
        except Exception as e:
            _log("  expr warn " + node.name + "." + name + " : " + str(e))
    return False


def _first_par(node, names, value):
    """Set the first parameter in `names` that exists on this build."""
    for n in names:
        if hasattr(node.par, n):
            return _setpar(node, n, value)
    _log("  none of " + str(names) + " on " + node.name)
    return False


def _first_expr(node, names, expr):
    for n in names:
        if hasattr(node.par, n):
            return _setexpr(node, n, expr)
    _log("  none of " + str(names) + " on " + node.name + " (expr)")
    return False


def _wire(src, dst, in_idx=0):
    """Connect src -> dst input `in_idx`. Both must be real OPs."""
    if src is None or dst is None:
        _log("  wire skip (missing op): " + str(src) + " -> " + str(dst))
        return False
    try:
        dst.inputConnectors[in_idx].connect(src)
        return True
    except Exception as e:
        _log("  wire warn " + src.name + " -> " + dst.name + "[" + str(in_idx) + "] : " + str(e))
        return False


# ---------------------------------------------------------------------
# preflight — report what we found before we touch anything
# ---------------------------------------------------------------------
def preflight():
    _log("=== preflight ===")
    ok = True
    if P is None:
        _log("FAIL  parent COMP not found (looked for " + P_PATH + " and any COMP with " + SRC + "/" + SYPHON + ")")
        return False
    _log("PASS  parent = " + P.path)
    for name, essential in ((SRC, True), (SYPHON, True), (AUDIO_SPECTRUM, False), (AUDIO_AMP, False)):
        found = P.op(name) is not None
        tag = "PASS" if found else ("FAIL" if essential else "WARN")
        if essential and not found:
            ok = False
        _log(tag + "  " + name + (" found" if found else " MISSING"))
    if P.op(AUDIO_SPECTRUM) is None and P.op(AUDIO_AMP) is None:
        _log("WARN  no audio source — kick/snare will stay idle until audio_spectrum or audio_amp exists")
    return ok


# ---------------------------------------------------------------------
# audio bands — one Script CHOP that always emits 'bass' and 'high'
# (index-based slicing == naming-agnostic, so it survives any spectrum layout)
# ---------------------------------------------------------------------
AUDIO_BANDS_CODE = '''# fx_audio_bands — emit averaged 'bass' and 'high' bands, naming-agnostic
def onCook(scriptOp):
    scriptOp.clear()
    src = op('%s')
    bass = 0.0
    high = 0.0
    if src is not None and src.numChans > 0:
        n = src.numChans
        lo = src.chans()[:max(1, n // 8)]          # low 1/8 of the spectrum
        hi = src.chans()[max(1, (3 * n) // 4):]    # top 1/4 of the spectrum
        if lo:
            bass = sum(c.eval() for c in lo) / len(lo)
        if hi:
            high = sum(c.eval() for c in hi) / len(hi)
    else:
        amp = op('%s')
        if amp is not None and amp.numChans > 0:
            bass = high = amp[0].eval()
    scriptOp.appendChan('bass').vals = [bass]
    scriptOp.appendChan('high').vals = [high]
    return
''' % (AUDIO_SPECTRUM, AUDIO_AMP)


def wire_audio_bands():
    _log("--- audio bands ---")
    cb = _op(textDAT, "fx_audio_bands_cb", 0, 0)
    cb.text = AUDIO_BANDS_CODE
    bands = _op(scriptCHOP, "fx_audio_bands", 1, 0)
    _setpar(bands, "callbacks", cb)
    return bands


# ---------------------------------------------------------------------
# evolution — LFOs, organic noise, 30 s beat-density accumulator -> master
# ---------------------------------------------------------------------
def wire_evolution(bands):
    _log("--- evolution ---")
    # three slow LFOs, each mapped 0..1 (amplitude .5 + offset .5)
    for name, hz, r in (("fx_lfo_hue", LFO_HUE_HZ, 0), ("fx_lfo_glow", LFO_GLOW_HZ, 1), ("fx_lfo_decay", LFO_DECAY_HZ, 2)):
        lfo = _op(lfoCHOP, name, 3, r)
        _setpar(lfo, "frequency", hz)
        _first_par(lfo, ["amplitude", "amp"], 0.5)
        _setpar(lfo, "offset", 0.5)

    # organic wobble — 2 uncorrelated channels for the shake direction
    noise = _op(noiseCHOP, "fx_noise", 3, 3)
    _first_par(noise, ["channelname", "channelnames"], "chan1 chan2")
    _setpar(noise, "period", 4.0)
    _setpar(noise, "amplitude", 1.0)

    # 30 s energy accumulator: long filter of the bass band == beat density
    energy = _op(filterCHOP, "fx_energy", 4, 0)
    _wire(bands, energy)
    _first_par(energy, ["width", "filterwidth"], EVO_WINDOW_S)

    # master intensity: map smoothed energy -> [EVO_MIN, EVO_MAX]
    master = _op(mathCHOP, "fx_master", 5, 0)
    _wire(energy, master)
    # select just the bass channel then scale into range
    _first_par(master, ["chanscope"], "bass")
    _first_par(master, ["torange1", "torangelow"], EVO_MIN)
    _first_par(master, ["torange2", "torangehigh"], EVO_MAX)
    _first_par(master, ["fromrange1", "fromrangelow"], 0.0)
    _first_par(master, ["fromrange2", "fromrangehigh"], 1.0)
    return master


# ---------------------------------------------------------------------
# palette — Table DAT of 4 palettes + Script CHOP crossfade -> tint TOP
# ---------------------------------------------------------------------
PALETTE_ENGINE_CODE = '''# fx_palette_engine — time-driven 4-palette crossfade
# emits primaryR/G/B and secondaryR/G/B, 3 s smooth crossfade between palettes
def onCook(scriptOp):
    scriptOp.clear()
    tbl = op('fx_palette_table')
    if tbl is None or tbl.numRows == 0:
        for nm in ('primaryR','primaryG','primaryB','secondaryR','secondaryG','secondaryB'):
            scriptOp.appendChan(nm).vals = [1.0]
        return
    n = tbl.numRows
    period = %f
    xfade = %f
    t = absTime.seconds
    pos = (t / period)
    idx = int(pos) %% n
    nxt = (idx + 1) %% n
    frac = pos - int(pos)                      # 0..1 within the current window
    # crossfade only during the last `xfade` seconds of the window
    edge = 1.0 - (xfade / period)
    if frac < edge:
        f = 0.0
    else:
        f = (frac - edge) / (1.0 - edge)
        f = f * f * (3.0 - 2.0 * f)            # smoothstep
    def cell(row, col):
        try:
            return float(tbl[row, col].val)
        except Exception:
            return 0.0
    names = ('primaryR','primaryG','primaryB','secondaryR','secondaryG','secondaryB')
    for col, nm in enumerate(names):
        a = cell(idx, col)
        b = cell(nxt, col)
        scriptOp.appendChan(nm).vals = [a + (b - a) * f]
    return
''' % (PALETTE_PERIOD_S, PALETTE_XFADE_S)


def wire_palette(src):
    _log("--- palette ---")
    tbl = _op(tableDAT, "fx_palette_table", 6, 0)
    tbl.clear()
    for pal in PALETTES:
        tbl.appendRow([("%0.4f" % v) for v in pal])
    cb = _op(textDAT, "fx_palette_engine_cb", 6, 1)
    cb.text = PALETTE_ENGINE_CODE
    engine = _op(scriptCHOP, "fx_palette_engine", 6, 2)
    _setpar(engine, "callbacks", cb)

    tint = _op(constantTOP, "fx_palette_tint", 7, 0)
    _setpar(tint, "resolutionw", OUT_W)
    _setpar(tint, "resolutionh", OUT_H)
    _first_par(tint, ["outputresolution"], "custom")
    _setexpr(tint, "colorr", "op('fx_palette_engine')['primaryR']")
    _setexpr(tint, "colorg", "op('fx_palette_engine')['primaryG']")
    _setexpr(tint, "colorb", "op('fx_palette_engine')['primaryB']")
    _setpar(tint, "alpha", 1.0)

    # multiply the palette tint onto the silhouette
    apply_ = _op(compositeTOP, "fx_palette_apply", 8, 0)
    _setpar(apply_, "operand", "multiply")
    _first_par(apply_, ["outputresolution"], "custom")
    _setpar(apply_, "resolutionw", OUT_W)
    _setpar(apply_, "resolutionh", OUT_H)
    _wire(src, apply_, 0)
    _wire(tint, apply_, 1)
    return apply_


# ---------------------------------------------------------------------
# trails — Feedback TOP with colour-drifting decay (see gotcha note up top)
# ---------------------------------------------------------------------
def wire_trails(src, master):
    _log("--- trails ---")
    fb = _op(feedbackTOP, "fx_trail_feedback", 9, 0)

    # decay + hue-drift on the FEEDBACK branch only (fresh source stays crisp)
    hsv = _op(hsvadjustTOP, "fx_trail_hsv", 10, 0)
    # value multiply == decay; evolution nudges it via fx_lfo_decay
    _first_expr(hsv, ["valuemult", "valuemultiply"],
                "%f - op('fx_lfo_decay')['chan1'] * 0.03" % TRAIL_DECAY)
    _first_expr(hsv, ["hueoffset", "hue"],
                "%f + op('fx_lfo_hue')['chan1'] * 0.002" % TRAIL_HUE_DRIFT)
    _first_par(hsv, ["saturationmult", "saturationmultiply", "saturation"], TRAIL_SAT)

    # composite: maximum(fresh source, decayed feedback) — order-independent
    comp = _op(compositeTOP, "fx_trail_comp", 11, 0)
    _setpar(comp, "operand", TRAIL_COMPOSITE)
    _first_par(comp, ["outputresolution"], "custom")
    _setpar(comp, "resolutionw", OUT_W)
    _setpar(comp, "resolutionh", OUT_H)

    # --- STRICT ORDER to defeat "Not enough sources specified" ---
    # a. wire BOTH composite inputs FIRST
    _wire(src, comp, 0)          # fresh silhouette
    _wire(hsv, comp, 1)          # decayed, hue-drifted trail
    # b. wire the feedback initialiser (its own input = the source)
    _wire(src, fb, 0)
    # c. feedback grabs last-frame from the composite
    _wire(fb, hsv, 0)
    # d. ONLY NOW close the loop by pointing the Feedback target at the composite
    if hasattr(fb.par, "top"):
        try:
            fb.par.top = comp
        except Exception:
            _setpar(fb, "top", comp.name) or _setpar(fb, "top", comp.path)
    _log("  feedback target set -> " + comp.name)
    return comp


# ---------------------------------------------------------------------
# kick flash — bass trigger -> radial expansion from centre, added over image
# ---------------------------------------------------------------------
def wire_kick(src, bands, master):
    _log("--- kick flash ---")
    sel = _op(selectCHOP, "fx_kick_sel", 4, 4)
    _wire(bands, sel)
    _first_par(sel, ["channames", "channelnames"], "bass")

    env = _op(triggerCHOP, "fx_kick_env", 5, 4)
    _wire(sel, env)
    _first_par(env, ["threshold", "triggerthreshold"], KICK_THRESH)
    _first_par(env, ["attack", "attacklength"], KICK_ATTACK)
    _first_par(env, ["release", "decay", "releaselength", "decayrate"], KICK_RELEASE)

    # radial expansion: scale the silhouette up on the flash, centred (~body CoM)
    expand = _op(transformTOP, "fx_kick_expand", 12, 0)
    _wire(src, expand, 0)
    _first_par(expand, ["outputresolution"], "custom")
    _setpar(expand, "resolutionw", OUT_W)
    _setpar(expand, "resolutionh", OUT_H)
    # pivot defaults to 0.5,0.5 == frame centre (good proxy for a centred body)
    scale_expr = "1 + op('fx_kick_env')['bass'] * %f * op('fx_master')['bass']" % KICK_INTENSITY
    if not _setexpr(expand, "scale", scale_expr):
        _setexpr(expand, "scalex", scale_expr)
        _setexpr(expand, "scaley", scale_expr)

    # brighten the expanded copy by the envelope so it reads as a flash
    bright = _op(levelTOP, "fx_kick_bright", 13, 0)
    _wire(expand, bright)
    _setexpr(bright, "brightness1", "1 + op('fx_kick_env')['bass'] * 1.5")
    _setexpr(bright, "opacity", "op('fx_kick_env')['bass']")

    # add the flash over the trails
    comp = _op(compositeTOP, "fx_kick_comp", 14, 0)
    _setpar(comp, "operand", "add")
    _first_par(comp, ["outputresolution"], "custom")
    _setpar(comp, "resolutionw", OUT_W)
    _setpar(comp, "resolutionh", OUT_H)
    _wire(src, comp, 0)
    _wire(bright, comp, 1)
    return comp


# ---------------------------------------------------------------------
# snare shake — high-freq trigger -> jitter (default) or GLSL RGB split
# ---------------------------------------------------------------------
SNARE_GLSL = '''// fx_snare_glsl — chromatic-aberration RGB split driven by uShake (0..1)
// uShake bound to uniform slot 0 (0-indexed uniname0 / value0x) per repo convention.
uniform float uShake;
out vec4 fragColor;
void main()
{
    vec2 uv = vUV.st;
    float px = uShake * %f * uTD2DInfos[0].res.z;   // res.z == 1.0/width
    float r = texture(sTD2DInputs[0], uv + vec2(px, 0.0)).r;
    float g = texture(sTD2DInputs[0], uv).g;
    float b = texture(sTD2DInputs[0], uv - vec2(px, 0.0)).b;
    float a = texture(sTD2DInputs[0], uv).a;
    fragColor = TDOutputSwizzle(vec4(r, g, b, a));
}
''' % SNARE_SHAKE_PX


def wire_snare(src, bands, master):
    _log("--- snare shake ---")
    sel = _op(selectCHOP, "fx_snare_sel", 4, 5)
    _wire(bands, sel)
    _first_par(sel, ["channames", "channelnames"], "high")

    env = _op(triggerCHOP, "fx_snare_env", 5, 5)
    _wire(sel, env)
    _first_par(env, ["threshold", "triggerthreshold"], SNARE_THRESH)
    _first_par(env, ["attack", "attacklength"], SNARE_ATTACK)
    _first_par(env, ["release", "decay", "releaselength", "decayrate"], SNARE_RELEASE)

    if USE_GLSL_RGB_SPLIT:
        _log("  snare mode: GLSL RGB split")
        srcdat = _op(textDAT, "fx_snare_glsl_src", 12, 4)
        srcdat.text = SNARE_GLSL
        glsl = _op(glslTOP, "fx_snare_glsl", 12, 5)
        _wire(src, glsl, 0)
        _first_par(glsl, ["outputresolution"], "custom")
        _setpar(glsl, "resolutionw", OUT_W)
        _setpar(glsl, "resolutionh", OUT_H)
        _setpar(glsl, "pixeldat", srcdat)
        # 0-indexed uniform slot (repo lesson: uniname0 / value0x), guarded
        _first_par(glsl, ["uniname0", "uniformname0"], "uShake")
        _first_expr(glsl, ["value0x"], "op('fx_snare_env')['high'] * op('fx_master')['bass']")
        try:
            if glsl.errors():
                _log("  GLSL reported errors — falling back to transform jitter")
                return _snare_jitter(src, env, master)
        except Exception:
            pass
        return glsl

    return _snare_jitter(src, env, master)


def _snare_jitter(src, env, master):
    _log("  snare mode: transform jitter")
    noise = P.op("fx_noise")  # created in wire_evolution
    shake = _op(transformTOP, "fx_snare_shake", 12, 0)
    _wire(src, shake, 0)
    _first_par(shake, ["outputresolution"], "custom")
    _setpar(shake, "resolutionw", OUT_W)
    _setpar(shake, "resolutionh", OUT_H)
    frac = SNARE_SHAKE_PX / float(OUT_W)  # transform t is a fraction of resolution
    nx = "op('fx_noise')[0]" if noise is not None else "0"
    ny = "op('fx_noise')[1]" if (noise is not None and noise.numChans > 1) else nx
    _setexpr(shake, "tx", "op('fx_snare_env')['high'] * %s * %f" % (nx, frac))
    _setexpr(shake, "ty", "op('fx_snare_env')['high'] * %s * %f" % (ny, frac))
    return shake


# ---------------------------------------------------------------------
# orchestration
# ---------------------------------------------------------------------
def build_effects():
    _log("=================================================")
    _log("extend_dj_graphics — building extended FX layer")
    _log("=================================================")
    if not preflight():
        _log("ABORT — preflight failed. Fix the FAIL lines above and re-paste.")
        return

    src0 = P.op(SRC)
    syphon = P.op(SYPHON)

    bands = wire_audio_bands()
    master = wire_evolution(bands)

    # signal order: palette -> trails -> kick -> snare -> out
    stage = wire_palette(src0)
    stage = wire_trails(stage, master)
    stage = wire_kick(stage, bands, master)
    stage = wire_snare(stage, bands, master)

    fx_out = _op(nullTOP, "fx_out", 15, 0)
    _wire(stage, fx_out, 0)

    # re-route syphon through the FX chain
    if syphon is not None:
        _wire(fx_out, syphon, 0)
        _log("re-routed " + SYPHON + " input -> fx_out")
    else:
        _log("WARN  " + SYPHON + " missing — connect fx_out to your output manually")

    _log("=================================================")
    _log("=== build_effects complete ===")
    _log("chain:  %s -> fx_palette_apply -> fx_trail_comp -> fx_kick_comp -> %s -> fx_out -> %s"
         % (SRC, ("fx_snare_glsl" if USE_GLSL_RGB_SPLIT else "fx_snare_shake"), SYPHON))
    _log("tune:   edit the CONFIG block at the top and re-paste (idempotent).")
    _log("trails not showing? set TRAIL_COMPOSITE='over' (needs alpha) or 'add'.")
    _log("remove: extend_dj_graphics_teardown()")


def extend_dj_graphics_teardown():
    """Rewire SYPHON back to SRC and delete every fx_* node this script made."""
    if P is None:
        _log("teardown: parent not found")
        return
    syphon, src0 = P.op(SYPHON), P.op(SRC)
    if syphon is not None and src0 is not None:
        _wire(src0, syphon, 0)
        _log("teardown: " + SYPHON + " restored -> " + SRC)
    killed = 0
    for child in list(P.children):
        if child.name.startswith("fx_"):
            child.destroy()
            killed += 1
    _log("teardown: removed %d fx_ nodes" % killed)


# auto-run on paste
build_effects()
