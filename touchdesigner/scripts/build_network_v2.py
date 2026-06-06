# build_network_v2.py — Programmatic TD network builder (clean rebuild)
# =====================================================================
# WHY THIS EXISTS
#   Both shipped 311 KB .toe files (dj_visuals.toe / .14.toe and the
#   dj_visuals.live_2026-04-18.* pair) regressed to a root network that
#   contains ONLY `noise_embers` — the canonical
#       body_mask_top -> edge_detect -> fire/lightning -> bloom -> syphonOut1
#   chain the audit assumed is gone. Rather than surgically repair a binary
#   .toe, this script rebuilds the whole pipeline from code so it is
#   reviewable in git and reproducible.
#
# HOW TO USE
#   1. In TouchDesigner open the Textport:  Alt+T
#   2. Make sure REPO_ROOT below points at this repo on THIS machine.
#   3. Paste this entire file into the Textport and press Enter, OR:
#        op('/project1').par.... ; exec(open('<path>/build_network_v2.py').read())
#   4. Watch the Textport log. Each operator prints as it is created.
#   5. Verify visually in /project1, then start the tracker:
#        ./venv/bin/python python/movement_tracker.py --max-people 1
#
# INTERFACE CONTRACT (surfaced from the Python side, 2026-06-05)
#   MASK TRANSPORT ....... shared memory mmap file
#     path ............... /tmp/djsam_bodymask.raw
#     layout ............. 4-byte uint32 LE frame counter  +  640*480 uint8
#                          row-major grayscale (MONO, not RGBA)
#     resolution ......... 640 x 480   (MASK_W x MASK_H)
#     TD receiver ........ Script TOP `body_mask_top`, 8-bit mono, callbacks
#                          DAT = segmentation_mask_reader.py (expands mono->RGBA)
#   OSC .................. udp 127.0.0.1 : 7000   (NOT 9000)
#     /visual/mode ....... float 0=flame 1=lightning  -> drives Switch TOP
#     /visual/mode_name .. string ("flame"/"lightning")
#     /movement/person{N}/{key} ... float per-joint coords + energy
#     /movement/person{N}/tracking_active ... 1.0/0.0
#     /movement/num_people ......... float
#     /movement/avg_energy ......... float  (usable as motion-energy uniform)
#     /movement/mask_active ........ 1.0 when a body mask is being written
#   AUDIO ............... NOTE: there is NO /audio/* OSC sender in this repo.
#     The README /audio/* lines are aspirational. In the proven pipeline the
#     audio-reactive uniforms (value1..value9) are computed INSIDE TD by
#     aura_compositor.py reading an Audio Spectrum CHOP every frame
#     (BlackHole 2ch -> audio_in -> audio_spectrum). This builder wires that
#     real path; it does NOT invent an `osc_audio` CHOP.
#   GLSL UNIFORMS ....... GLSL TOP pairs `uniformname1..10` (names) with
#     `value1..10` (per-frame floats). Mapping (shared by both shaders):
#       1 uFlameIntensity 2 uTurbulence 3 uDistortion 4 uSparkle
#       5 uMotionEnergy   6 uBassEnergy 7 uMidEnergy  8 uHighEnergy
#       9 uBurstDecay     10 uTime
#   SHADERS ............. touchdesigner/shaders/fire_aura.glsl
#                        touchdesigner/shaders/lightning.glsl  (shipped PR #1)
#   SYPHON OUT .......... Syphon Spout Out TOP `syphonOut1`,
#                        sender name "TDSyphonSpoutOut" (OBS adds a
#                        "Syphon Client" source pointing at this name).
#
# This script ONLY builds operators. It does not touch any .toe on disk.
# =====================================================================

import os

# --- EDIT THIS if the repo lives elsewhere on the machine running TD ---
REPO_ROOT = "/Users/thomasadair/projects/touchdesigner-dj-suite"

SHADER_DIR = os.path.join(REPO_ROOT, "touchdesigner", "shaders")
SCRIPT_DIR = os.path.join(REPO_ROOT, "touchdesigner", "scripts")
FIRE_GLSL = os.path.join(SHADER_DIR, "fire_aura.glsl")
LIGHT_GLSL = os.path.join(SHADER_DIR, "lightning.glsl")
MASK_READER = os.path.join(SCRIPT_DIR, "segmentation_mask_reader.py")
COMPOSITOR = os.path.join(SCRIPT_DIR, "aura_compositor.py")

MASK_W, MASK_H = 640, 480  # must match movement_tracker.py
OUT_W, OUT_H = 1280, 720  # shader / final output resolution
OSC_PORT = 7000
SYPHON_NAME = "TDSyphonSpoutOut"

# Uniform-name -> slot mapping shared by both shaders.
UNIFORM_NAMES = [
    "uFlameIntensity",  # value1
    "uTurbulence",  # value2
    "uDistortion",  # value3
    "uSparkle",  # value4
    "uMotionEnergy",  # value5
    "uBassEnergy",  # value6
    "uMidEnergy",  # value7
    "uHighEnergy",  # value8
    "uBurstDecay",  # value9
    "uTime",  # value10
]

ROOT = op("/project1")


def _log(msg):
    print("[build_v2] " + msg)


def _make(op_type, name, x, y):
    """Create (or reuse) `name` under /project1 and lay it out at (x, y)."""
    existing = ROOT.op(name)
    if existing is not None:
        _log("reuse  " + name + " (" + existing.type + ")")
        node = existing
    else:
        node = ROOT.create(op_type, name)
        _log("create " + name + " (" + node.type + ")")
    node.nodeX, node.nodeY = x, y
    return node


def _text_dat_from_file(name, file_path, x, y):
    """Text DAT whose contents are synced from a file on disk."""
    dat = _make(textDAT, name, x, y)
    if os.path.exists(file_path):
        dat.par.file = file_path
        dat.par.syncfile = True
        try:
            dat.par.loadonstartpulse.pulse()
        except Exception as e:
            _log("  loadonstart pulse failed for " + name + ": " + str(e))
    else:
        _log("  !! file missing: " + file_path)
    return dat


def _glsl_uniform_diag(glsl):
    """Dump the GLSL TOP's real uniform-related par names + sequence groups so
    we can confirm the exact API on this TD build (2022.35320) instead of
    guessing. Printed only when a grow is actually needed."""
    try:
        names = sorted({p.name for p in glsl.pars("uniformname*", "value*", "const*")})
        _log(
            "  [diag] %s uniform-ish pars: %s" % (glsl.name, names if names else "NONE")
        )
    except Exception as e:
        _log("  [diag] %s par-list err: %s" % (glsl.name, str(e)))
    try:
        groups = []
        for sg in glsl.seq:
            try:
                groups.append("%s(numBlocks=%s)" % (sg.name, sg.numBlocks))
            except Exception:
                groups.append(str(sg))
        _log("  [diag] %s seq groups: %s" % (glsl.name, groups if groups else "NONE"))
    except Exception as e:
        _log("  [diag] %s seq-list err: %s" % (glsl.name, str(e)))


def _ensure_glsl_uniform_slots(glsl, n):
    """Grow a GLSL TOP's uniform sequence so uniformname1..n / value1..n exist.
    A stock GLSL TOP ships ~6 slots; the pipeline needs 10. We don't assume the
    sequence's name or block-par names (they vary by TD version): instead we
    test-grow each sequence group and KEEP the one whose growth makes
    `uniformname{n}` materialize, reverting the rest. Falls back to a numeric
    count par. Logs the real names via [diag] so a failure is actionable.
    """
    target = "uniformname" + str(n)
    if getattr(glsl.par, target, None) is not None:
        return True
    _glsl_uniform_diag(glsl)
    grown = False
    # Test-grow-and-verify each sequence group.
    try:
        for sg in glsl.seq:
            try:
                before = sg.numBlocks
                if before >= n:
                    continue
                sg.numBlocks = n
                if getattr(glsl.par, target, None) is not None:
                    grown = True
                    _log(
                        "  grew GLSL uniform seq '%s' -> %d blocks"
                        % (sg.name, sg.numBlocks)
                    )
                    break
                sg.numBlocks = before  # wrong group — revert
            except Exception as e:
                _log("  seq grow attempt err on %s: %s" % (glsl.name, str(e)))
    except Exception as e:
        _log("  uniform-seq discovery err: " + str(e))
    # Fallback: some TD versions gate the count behind a single numeric par.
    if getattr(glsl.par, target, None) is None:
        for cnt in ("numuniforms", "numconstants", "uniforms", "numvecuniforms"):
            par = getattr(glsl.par, cnt, None)
            if par is not None:
                try:
                    par.val = n
                    _log("  set GLSL count par '%s' = %d" % (cnt, n))
                except Exception as e:
                    _log("  count par '%s' set err: %s" % (cnt, str(e)))
                break
    if getattr(glsl.par, target, None) is None:
        _log(
            "  WARN %s: uniform slots still < %d after grow attempts — "
            "see [diag] above for the real par/seq names" % (glsl.name, n)
        )
        return False
    return grown


def build():
    _log("=== building canonical v2 network under /project1 ===")

    # ----------------------------------------------------------------
    # 1. MASK RECEIVER  — Script TOP reads the mmap and outputs body_mask_top
    # ----------------------------------------------------------------
    reader_dat = _text_dat_from_file("segmentation_mask_reader", MASK_READER, -800, 400)
    body_mask = _make(scriptTOP, "body_mask_top", -600, 400)
    body_mask.par.callbacks = reader_dat  # cook()/setup() callbacks
    try:
        body_mask.par.resolutionw = MASK_W
        body_mask.par.resolutionh = MASK_H
    except Exception as e:
        _log("  body_mask res set warn: " + str(e))

    # ----------------------------------------------------------------
    # 2. EDGE + (optional) small blur. The Python side already emits a THIN
    #    contour (MORPH_GRADIENT), so the Edge TOP is light and edge_blur is a
    #    tiny kernel just to soften aliasing. Either can be bypassed.
    # ----------------------------------------------------------------
    edge = _make(edgeTOP, "edge_detect", -400, 400)
    edge.setInputs([body_mask])
    # Upscale to canvas size HERE. body_mask_top is locked to MASK_W x MASK_H
    # (640x480) by the segmentation_mask_reader callback (copyNumpyArray +
    # setup() force the Script TOP resolution to match the mmap array), so the
    # mask itself must stay 640x480. edge_detect is the first TOP we can resize:
    # render it at OUT_W x OUT_H so the contour fills the 1280x720 Syphon canvas
    # instead of living in a 640x480 corner. Everything downstream inherits this.
    try:
        edge.par.outputresolution = "custom"
        edge.par.resolutionw = OUT_W
        edge.par.resolutionh = OUT_H
    except Exception as e:
        _log("  edge_detect res set warn: " + str(e))

    edge_blur = _make(blurTOP, "edge_blur", -250, 400)
    edge_blur.setInputs([edge])
    try:
        edge_blur.par.size = 1.0  # small — contour is already thin
        edge_blur.par.outputresolution = "custom"
        edge_blur.par.resolutionw = OUT_W
        edge_blur.par.resolutionh = OUT_H
    except Exception as e:
        _log("  edge_blur res set warn: " + str(e))

    # Black Constant TOP for GLSL inputs 1 & 2. BOTH shaders sample
    # sTD2DInputs[1] and sTD2DInputs[2]; TD sizes sTD2DInputs[] to the
    # CONNECTED-input count, so wiring only input 0 made indices 1/2
    # out-of-range -> "GLSL Shader has compile errors". The shaders read
    # those inputs as max(uEnergyUniform, texture(...).r), so feeding BLACK
    # makes the uniform dominate (the intended "optional spatial modulation"
    # default) while keeping all three sampler indices valid.
    zero_src = _make(constantTOP, "zero_src", -250, 400)
    try:
        zero_src.par.colorr = 0.0
        zero_src.par.colorg = 0.0
        zero_src.par.colorb = 0.0
        zero_src.par.alpha = 0.0
        # Match the GLSL output / contour resolution (OUT_W x OUT_H). Mismatched
        # GLSL input sizes (640x480 black vs 1280x720 contour) are part of why
        # the output landed in a corner — keep all three GLSL inputs the same.
        zero_src.par.outputresolution = "custom"
        zero_src.par.resolutionw = OUT_W
        zero_src.par.resolutionh = OUT_H
    except Exception as e:
        _log("  zero_src param warn: " + str(e))

    # ----------------------------------------------------------------
    # 3+4. GLSL TOPs — fire + lightning. Same input shape, same uniform
    #      contract, so the Switch can swap them with zero re-wiring.
    #      Input 0 = contour mask; inputs 1/2 = black (uniforms dominate).
    # ----------------------------------------------------------------
    fire_src = _text_dat_from_file("fire_aura_src", FIRE_GLSL, -250, 250)
    light_src = _text_dat_from_file("lightning_src", LIGHT_GLSL, -250, 100)

    def _glsl(name, src_dat, y):
        g = _make(glslTOP, name, -50, y)
        g.par.pixeldat = src_dat
        try:
            g.par.outputresolution = "custom"
            g.par.resolutionw = OUT_W
            g.par.resolutionh = OUT_H
            g.par.format = "rgba16float"
        except Exception as e:
            _log("  " + name + " res/format warn: " + str(e))
        # input 0 = contour; 1 & 2 = black so sTD2DInputs[1]/[2] exist
        # (prevents the sampler-index-out-of-range compile error).
        g.setInputs([edge_blur, zero_src, zero_src])
        # A stock GLSL TOP ships with only ~6 uniform slots; we need 10
        # (uniformname1..10 / value1..10). Grow the uniform parameter
        # sequence FIRST, otherwise uniformname7..10 don't exist yet.
        _ensure_glsl_uniform_slots(g, len(UNIFORM_NAMES))
        # Map uniform names into the GLSL TOP's uniformname1..10 slots.
        # value1..10 are written every frame by aura_compositor.py.
        for i, uname in enumerate(UNIFORM_NAMES, start=1):
            par = getattr(g.par, "uniformname" + str(i), None)
            if par is not None:
                par.val = uname
            else:
                _log("  " + name + ": uniformname" + str(i) + " slot STILL missing")
        return g

    fire_glsl = _glsl("fire_aura_glsl", fire_src, 250)
    light_glsl = _glsl("lightning_glsl", light_src, 100)

    # ----------------------------------------------------------------
    # 5. OSC IN — movement + visual/mode arrive here on port 7000.
    #    (Audio is NOT OSC — see header. This CHOP carries /visual/mode for
    #     the Switch and /movement/* for the motion-energy uniform.)
    # ----------------------------------------------------------------
    oscin = _make(oscinCHOP, "oscin1", -600, -100)
    try:
        oscin.par.port = OSC_PORT
        oscin.par.active = True
    except Exception as e:
        _log("  oscin1 param warn: " + str(e))

    # ----------------------------------------------------------------
    # 5b. AUDIO ANALYSIS (the REAL uniform source). BlackHole 2ch ->
    #     audio_in -> audio_spectrum. aura_compositor.py reads audio_spectrum
    #     every frame and pushes value1..value9 into both GLSL TOPs.
    # ----------------------------------------------------------------
    audio_in = _make(audiodeviceinCHOP, "audio_in", -800, -100)
    try:
        audio_in.par.active = True
    except Exception:
        pass
    audio_spectrum = _make(audiospectrumCHOP, "audio_spectrum", -600, -250)
    audio_spectrum.setInputs([audio_in])

    # aura_compositor.py is an EXECUTE DAT (not a Text DAT): it runs on Frame
    # Start, reads audio_spectrum, and writes value1..value9 into both GLSL
    # TOPs each frame. Create it as executeDAT so the onFrameStart callback
    # actually fires — a Text DAT would just sit there inert.
    compositor = _make(executeDAT, "aura_compositor", -400, -250)
    if os.path.exists(COMPOSITOR):
        with open(COMPOSITOR) as _f:
            compositor.text = _f.read()
    else:
        _log("  !! aura_compositor source missing: " + COMPOSITOR)
    # Enable the Frame Start callback + activate. Execute DAT par names:
    # active, start, create, exit, framestart, frameend, play.
    for pname in ("active", "framestart"):
        par = getattr(compositor.par, pname, None)
        if par is not None:
            try:
                par.val = True
                _log("  aura_compositor.%s = True" % pname)
            except Exception as e:
                _log("  aura_compositor.%s set err: %s" % (pname, str(e)))
        else:
            _log("  aura_compositor: par '%s' missing — set manually" % pname)

    # ----------------------------------------------------------------
    # 6. SWITCH — index from /visual/mode (0=flame, 1=lightning).
    #    OSC In CHOP names the channel by its address: '/visual/mode'.
    # ----------------------------------------------------------------
    visual_switch = _make(switchTOP, "visual_switch", 450, 175)
    visual_switch.setInputs([fire_glsl, light_glsl])
    try:
        # Bind the switch index to the live OSC channel. Falls back to 0.
        visual_switch.par.index.expr = (
            "int(op('oscin1')['/visual/mode']) "
            "if op('oscin1') and '/visual/mode' in op('oscin1').chans() else 0"
        )
    except Exception as e:
        _log(
            "  switch index expr warn (set manually to oscin1 /visual/mode): " + str(e)
        )

    # ----------------------------------------------------------------
    # 7. BLOOM — MODEST per audit (blur size ~3, not 12). Blur -> Composite(add)
    #    back over the switched look. Keeps glow without washing the contour.
    # ----------------------------------------------------------------
    bloom_blur = _make(blurTOP, "bloom_blur", 650, 100)
    bloom_blur.setInputs([visual_switch])
    try:
        bloom_blur.par.size = 3.0  # AUDIT: modest 2-4, was 12
    except Exception:
        pass

    bloom_post = _make(compositeTOP, "bloom_post", 850, 175)
    bloom_post.setInputs([visual_switch, bloom_blur])  # original + glow
    try:
        bloom_post.par.operand = "add"
    except Exception:
        pass

    # final_composite is a single-source PASSTHROUGH (Null TOP). bloom_post
    # already produced the finished look (switched shader + glow via
    # Composite "add", 2 inputs). A Composite TOP needs >=2 inputs for ANY
    # operation, so a 1-input Composite here threw "Not enough sources
    # specified" and starved syphonOut1. A Null passes bloom_post straight
    # through at its OUT_W x OUT_H resolution.
    #   NOTE: the canonical aura_compositor docstring describes compositing the
    #   aura OVER a live `camera_in`. We deliberately DON'T add a camera here:
    #   OBS already owns the webcam source, and a second camera in TD would
    #   double-image (see diagnose_obs_double_image.py). The Syphon output is
    #   the aura/outline look only; OBS layers it over its own camera. If you
    #   ever want TD to do the over-camera composite, replace this Null with a
    #   Composite TOP (operand="over") wired [bloom_post, camera_in].
    final_composite = _make(nullTOP, "final_composite", 1050, 175)
    final_composite.setInputs([bloom_post])

    # ----------------------------------------------------------------
    # 8. SYPHON OUT — single sender OBS connects to. Exactly ONE Syphon Out
    #    (multiple senders = OBS double-image, see diagnose_obs_double_image.py).
    # ----------------------------------------------------------------
    syphon = _make(syphonspoutoutTOP, "syphonOut1", 1250, 175)
    syphon.setInputs([final_composite])
    try:
        syphon.par.sendername = SYPHON_NAME
        syphon.par.active = True
    except Exception as e:
        _log(
            "  syphon param warn (set sendername="
            + SYPHON_NAME
            + " manually): "
            + str(e)
        )

    _log("=== build complete ===")
    _log(
        "Next: select BlackHole 2ch on audio_in (only remaining manual touch), "
        "then start movement_tracker.py."
    )
    _log('OBS: add a Syphon Client source -> "' + SYPHON_NAME + '".')


build()
