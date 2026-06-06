# aura_compositor.py — Execute DAT / Timer Callback
# ====================================================
# [SYNCFILE-PROBE-V12] — 2026-04-23: Direct spectrum reading.
# ARCHITECTURE CHANGE: Audio is now computed directly from audio_spectrum
# every frame in onFrameStart. audio_params/audio_reactive_mapper are NO
# LONGER needed for the visual pipeline (they can still run for monitoring).
print(
    "[syncfile-probe-v12] aura_compositor.py loaded — direct spectrum audio path active"
)
# ====================================================
# Final compositing pipeline controller for the fire body aura.
# Runs every frame and orchestrates all the aura pipeline operators:
#   body mask → edge → particles → fire shader → bloom → composite
#
# Audio is read DIRECTLY from audio_spectrum every frame. This replaces
# the prior approach of reading from audio_params (Constant CHOP written
# by audio_reactive_mapper CHOP Execute DAT), which was unreliable because
# onValueChange was not firing.
#
# SETUP IN TOUCHDESIGNER:
#   1. Create Execute DAT  →  name: "aura_compositor"
#      - Paste this script
#      - Execute on: Frame Start = ON  (checkbox)
#      - Active: ON
#
#   2. Required operators:
#      - audio_spectrum      (Audio Spectrum CHOP — source of truth for audio)
#      - body_mask_top       (Script TOP — segmentation mask)
#      - edge_detect         (Edge TOP — body silhouette edge)
#      - noise_embers        (Noise TOP — ember texture layer)
#      - fire_aura_glsl      (GLSL TOP — fire shader)
#      - bloom_blur          (Blur TOP — glow pass)
#      - bloom_post          (Composite TOP — add glow back)
#      - camera_in           (Video Device In TOP — live camera feed)
#      - final_composite     (Composite TOP — over operation)
#      - body_channels       (Constant CHOP — from osc_body_receiver)
# ====================================================

import math

# ---- [AUDIO-FIX-2026-04-26 / AUDIO-FIX-2026-06-05] audio_in device on load ----
# 2026-04-26 (superseded): force-set audio_in to BlackHole 2ch every load.
# 2026-06-05: Serato master is physically patched into PreSonus Studio 1824c
# inputs 1-2 (OBS already captures it there); BlackHole never receives signal.
# Now prefer the '1824' device (matches "Studio 1824c", "PreSonus Studio 1824c"
# across TD versions). Fall back to BlackHole, then leave the menu default if the
# 1824c is unplugged. Input 1 = ch 1, Input 2 = ch 2 on the 1824c.
try:
    _fix_ai = op("/project1/audio_in")
    if _fix_ai is not None:
        _fix_ai.par.driver = "default"
        _fix_ai.cook(force=True)
        _fix_names = list(_fix_ai.par.device.menuNames or [])
        _fix_dev = next(
            (n for n in _fix_names if "1824" in (n or "").lower()), None
        ) or next((n for n in _fix_names if "blackhole" in (n or "").lower()), None)
        if _fix_dev:
            _fix_ai.par.device = _fix_dev
            _fix_ai.cook(force=True)
            print(
                "[AUDIO-FIX] device set to",
                _fix_dev,
                "| active:",
                _fix_ai.par.active.val,
            )
        else:
            print(
                "[AUDIO-FIX] no 1824c/BlackHole in devices, left default:", _fix_names
            )
    else:
        print("[AUDIO-FIX] audio_in op not found")
except Exception as _fix_e:
    print("[AUDIO-FIX] error:", _fix_e)
# -----------------------------------------------------------------------

# ---- ONE-SHOT AUDIO CHAIN BOOTSTRAP ----
_AUDIO_BOOTSTRAP_DONE = False
_RENDER_DIAG_DONE = False
_MASK_READER_RELOADED = False
_UNIFORMS_WIRED = False

# ============================================================
# AUDIO STATE — persistent across frames, computed in onFrameStart
# ============================================================
# Frequency bin ranges: audio_spectrum CHOP has ~22050 samples → 1 Hz/bin
BASS_BINS = (20, 200)  # 20–200 Hz
MID_BINS = (200, 2000)  # 200 Hz–2 kHz
HIGH_BINS = (2000, 20000)  # 2–20 kHz

# Per-band exponential smoothing (0=none, 0.99=very smooth)
BASS_SMOOTH_COEF = 0.85
MID_SMOOTH_COEF = 0.80
HIGH_SMOOTH_COEF = 0.75

# Onset detection
ONSET_THRESHOLD = 0.00005  # min bass energy jump to trigger
ONSET_COOLDOWN_MS = 120  # ms minimum between triggers
ONSET_DECAY_RATE = 0.92  # burst decay per frame

# Visual multipliers — calibrated 2026-04-23 against DDJ-SX2 noise floor
# noise_bass≈0.00081, noise_high≈0.0063.
# At noise floor: flame≈0.16 (dim), sparkle≈0.05 (barely visible)
# At full kick: bass ~10x noise → flame ≈ 1.6 (clamped to 1 in shader)
FLAME_INTENSITY_MULT = 200.0
TURBULENCE_MULT = 150.0
DISTORTION_MULT = 150.0
SPARKLE_MULT = 8.0
BLOOM_MULT = 25.0

# Mutable audio state (updated every frame)
_smooth_bass = 0.0
_smooth_mid = 0.0
_smooth_high = 0.0
_prev_bass = 0.0
_burst_decay = 0.0
_last_onset_frame = -999


def _band_energy(spectrum_chop, lo, hi):
    """Average magnitude of spectrum bins [lo, hi] (inclusive)."""
    if spectrum_chop is None or spectrum_chop.numSamples == 0:
        return 0.0
    n = spectrum_chop.numSamples
    lo = max(0, min(lo, n - 1))
    hi = max(0, min(hi, n - 1))
    chan = spectrum_chop[0]  # left/mono channel
    total = 0.0
    for i in range(lo, hi + 1):
        total += abs(chan[i])
    return total / max(hi - lo + 1, 1)


def _wire_glsl_uniforms_once():
    """Populate fire_aura_glsl.par.uniformname1..10 with the uniform names
    the fire_aura.glsl shader expects. Without these mappings the per-frame
    glsl.par.value1..9 writes go nowhere and the shader sees zeros.
    Fires exactly once per aura_compositor reload.
    """
    global _UNIFORMS_WIRED
    if _UNIFORMS_WIRED:
        return
    _UNIFORMS_WIRED = True
    try:
        glsl = op("/project1/fire_aura_glsl")
        if glsl is None:
            print("[uniforms] fire_aura_glsl MISSING — cannot wire")
            return
        names = [
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
        # Par names are 0-INDEXED on this TD build: uniname0..9 (NOT
        # uniformname1..). 16 slots already exist; just assign the first 10.
        for i, n in enumerate(names):  # i = 0..9
            par = getattr(glsl.par, "uniname" + str(i), None)
            if par is None:
                print("[uniforms] uniname" + str(i) + " MISSING on fire_aura_glsl")
                continue
            if par.val != n:
                par.val = n
                print("[uniforms] set uniname" + str(i) + " = " + n)
            else:
                print("[uniforms] uniname" + str(i) + " already = " + n)
        try:
            glsl.cook(force=True)
        except Exception as e:
            print("[uniforms] force cook err:", e)
        errs = (glsl.errors() or "").strip()
        if errs:
            print("[uniforms] fire_aura_glsl ERR: " + errs[:240])
        else:
            print("[uniforms] fire_aura_glsl no errors. wiring complete.")
    except Exception as e:
        print("[uniforms] fatal:", e)


def _force_reload_mask_reader_once():
    """Force segmentation_mask_reader DAT to reload its Python source from disk,
    then reset its Script TOP's cached mmap handle and force a cook.
    This is needed when segmentation_mask_reader.py has been edited on disk
    but TD's syncfile hasn't fired the hot-reload (which has been flaky).
    Fires exactly once per aura_compositor reload.
    """
    global _MASK_READER_RELOADED
    if _MASK_READER_RELOADED:
        return
    _MASK_READER_RELOADED = True
    try:
        dat = op("/project1/segmentation_mask_reader")
        top = op("/project1/body_mask_top")
        if dat is None or top is None:
            print("[mask-reload] segmentation_mask_reader or body_mask_top MISSING")
            return
        # Try to discover the on-disk source path from the DAT's file parameter.
        src_path = None
        try:
            if hasattr(dat.par, "file"):
                src_path = dat.par.file.eval()
        except Exception:
            pass
        if not src_path:
            # Known-good fallback
            src_path = (
                "/Users/thomasadair/projects/touchdesigner-dj-suite"
                "/touchdesigner/scripts/segmentation_mask_reader.py"
            )
        print("[mask-reload] reloading from: " + str(src_path))
        with open(src_path, "r") as fh:
            dat.text = fh.read()
        # Invalidate the Script TOP's cached mmap handle so it reopens with the
        # new HEADER_SIZE. Calling setup() via the unload/cook cycle does this.
        try:
            top.cook(force=True)
        except Exception as e:
            print("[mask-reload] force cook failed: " + str(e))
        print(
            "[mask-reload] OK. body_mask_top res="
            + str(top.width)
            + "x"
            + str(top.height)
            + " errs="
            + (top.errors() or "").strip()[:120]
        )
    except Exception as e:
        print("[mask-reload] fatal: " + str(e))


def _diag_render_chain_once():
    """One-shot render-pipeline diagnostic.
    Dumps cook state, errors, warnings, resolution, and input wiring for
    every TOP in the render chain, plus the Syphon output endpoint.
    Goal: find WHY the syphon client in OBS is frozen / no graphics.
    """
    global _RENDER_DIAG_DONE
    if _RENDER_DIAG_DONE:
        return
    _RENDER_DIAG_DONE = True
    try:
        # Ordered from source to final syphon output.
        chain = [
            "body_mask_top",
            "edge_detect",
            "edge_blur",
            "noise_embers",
            "motion_energy_top",
            "audio_energy_top",
            "fire_aura_shader_code",
            "fire_aura_glsl",
            "flame_layers",
            "bloom_blur",
            "bloom_post",
            "burst_flash",
            "camera_in",
            "final_composite",
            "output",
            "syphonOut1",
            "syphonspoutOut1",
            "syphonout1",
            "out1",
        ]
        print("\n[render-diag] === RENDER CHAIN STATE ===")
        for n in chain:
            o = op("/project1/" + n)
            if o is None:
                print("[render-diag] " + n + ": MISSING")
                continue
            # Pull diagnostic info safely
            try:
                errs = (o.errors() or "").strip()
            except Exception as e:
                errs = "<err-fetch:" + str(e) + ">"
            try:
                warns = (o.warnings() or "").strip()
            except Exception as e:
                warns = "<warn-fetch:" + str(e) + ">"
            try:
                w = o.width
                h = o.height
            except Exception:
                w = h = "?"
            # Cook info
            try:
                ct = o.cookTime
            except Exception:
                ct = "?"
            try:
                cooked = o.cookedThisFrame
            except Exception:
                cooked = "?"
            # Input wiring
            try:
                ins = []
                for i, ic in enumerate(o.inputConnectors):
                    src = None
                    try:
                        if ic.connections:
                            src = ic.connections[0].owner.name
                    except Exception:
                        pass
                    ins.append(str(i) + "=" + (src or "-"))
                inputs_s = ",".join(ins) if ins else "none"
            except Exception:
                inputs_s = "?"
            # Bypass / active
            try:
                bypass = bool(o.par.bypass.val) if hasattr(o.par, "bypass") else False
            except Exception:
                bypass = False

            print(
                "[render-diag] "
                + n
                + " | res="
                + str(w)
                + "x"
                + str(h)
                + " | in="
                + inputs_s
                + " | cookT="
                + str(ct)
                + " | cookedThisFrame="
                + str(cooked)
                + " | bypass="
                + str(bypass)
                + (" | ERR=" + errs if errs else "")
                + (" | WARN=" + warns if warns else "")
            )

        # Syphon-specific params (sender name + active)
        for syn_name in ["syphonOut1", "syphonspoutOut1", "syphonout1"]:
            s = op("/project1/" + syn_name)
            if s is None:
                continue
            try:
                pars = {}
                for pn in ("sendername", "active", "sendername0", "senderName"):
                    if hasattr(s.par, pn):
                        pars[pn] = getattr(s.par, pn).val
                print("[render-diag] " + syn_name + " pars: " + str(pars))
            except Exception as e:
                print("[render-diag] " + syn_name + " par-err:", e)

        # Also dump what's directly feeding each Syphon candidate's input 0
        for syn_name in ["syphonOut1", "syphonspoutOut1", "syphonout1"]:
            s = op("/project1/" + syn_name)
            if s is None:
                continue
            try:
                ic = s.inputConnectors[0]
                src = ic.connections[0].owner if ic.connections else None
                print(
                    "[render-diag] "
                    + syn_name
                    + " <- "
                    + (src.path if src else "NOTHING CONNECTED")
                )
            except Exception as e:
                print("[render-diag] " + syn_name + " wiring-err:", e)

        # Walk all children of /project1 and flag any operator with an error
        try:
            root = op("/project1")
            bad = []
            if root is not None:
                for child in root.children:
                    try:
                        e = (child.errors() or "").strip()
                        if e:
                            bad.append((child.name, e[:160]))
                    except Exception:
                        pass
            print("[render-diag] project1 error-badge count:", len(bad))
            for nm, msg in bad:
                print("[render-diag]   ERR " + nm + ": " + msg)
        except Exception as e:
            print("[render-diag] child-scan err:", e)

        print("[render-diag] === END ===\n")
    except Exception as e:
        print("[render-diag] fatal:", e)


def _bootstrap_audio_chain_once():
    global _AUDIO_BOOTSTRAP_DONE
    if _AUDIO_BOOTSTRAP_DONE:
        return
    try:
        ai = op("/project1/audio_in")
        asp = op("/project1/audio_spectrum")
        arm = op("/project1/audio_reactive_mapper")
        if ai is None:
            print("[bootstrap] audio_in not found")
            _AUDIO_BOOTSTRAP_DONE = True
            return

        # 1. Driver: force 'default' (which is CoreAudio on macOS)
        try:
            if ai.par.driver.val != "default":
                ai.par.driver = "default"
                print("[bootstrap] driver -> default")
        except Exception as e:
            print("[bootstrap] driver set err:", e)

        # Force cook so device menu refreshes under the new driver
        ai.cook(force=True)

        # 2. Enumerate devices and print full list
        dev_names = list(ai.par.device.menuNames or [])
        dev_labels = list(ai.par.device.menuLabels or [])

        def _find(*kws):
            for kw in kws:
                kl = kw.lower()
                for lab, nm in zip(dev_labels, dev_names):
                    if kl in (lab or "").lower() or kl in (nm or "").lower():
                        return nm
            return None

        # Ordered preference (2026-06-05 fix — supersedes 2026-04-26):
        #   1. PreSonus Studio 1824c — Serato master is physically patched into
        #      1824c inputs 1-2 (OBS already captures it there). This is the
        #      proven live signal path. Match on '1824' substring.
        #   2. Pioneer DDJ-SX2 — USB audio interface (some Serato configs route
        #      the master mix here directly).
        #   3. BlackHole 2ch — virtual loopback fallback (only carries signal if
        #      an app deliberately targets the "DJ + Analysis" multi-output; in
        #      Thomas's setup it is silent, so it is now a last-resort fallback).
        #   4. Built-in mic — last-resort fallback.
        chosen = (
            _find("1824c", "1824", "studio 1824", "presonus")
            or _find("ddj-sx2", "ddj sx2", "pioneer ddj", "ddj")
            or _find("blackhole", "loopback audio", "sound siphon")
            or _find(
                "built-in microphone", "internal microphone", "macbook", "built-in"
            )
            or _find("applehdaengineinput")  # built-in mic by UID substring
        )

        print("[bootstrap] === audio device enumeration ===")
        for lab, nm in zip(dev_labels, dev_names):
            marker = "  <== CHOSEN" if nm == chosen else ""
            print("[bootstrap]   label=" + str(lab) + " | name=" + str(nm) + marker)

        if chosen:
            try:
                if ai.par.device.val != chosen:
                    ai.par.device = chosen
                    print("[bootstrap] device SET -> " + str(chosen))
                else:
                    print("[bootstrap] device already " + str(chosen))
            except Exception as e:
                print("[bootstrap] device set err:", e)
        else:
            print(
                "[bootstrap] WARN no priority match, leaving device as "
                + str(ai.par.device.val)
            )

        # 3. Activate + cook
        if not ai.par.active.val:
            ai.par.active = True
            print("[bootstrap] audio_in.active = True")
        ai.cook(force=True)

        # 4. Spectrum cook
        if asp is not None:
            asp.cook(force=True)

        # 5. Mapper: watch spectrum, fire onValueChange, activate
        if arm is not None:
            try:
                if arm.par.chop.val != "audio_spectrum":
                    arm.par.chop = "audio_spectrum"
            except Exception:
                pass
            try:
                if not arm.par.valuechange.val:
                    arm.par.valuechange = True
            except Exception:
                pass
            try:
                if not arm.par.active.val:
                    arm.par.active = True
            except Exception:
                pass

        # 6. Report
        errs = ai.errors() or ""
        warns = ai.warnings() or ""
        print(
            "[bootstrap] FINAL: driver="
            + str(ai.par.driver.val)
            + " | device="
            + str(ai.par.device.val)
            + " | active="
            + str(ai.par.active.val)
            + (" | ERR=" + errs if errs else "")
            + (" | WARN=" + warns if warns else "")
        )
        if asp is not None:
            try:
                c0 = asp[0]
                if c0 is not None and len(c0) > 0:
                    mx = max(abs(c0[i]) for i in range(len(c0)))
                    print("[bootstrap] audio_spectrum max bin: " + str(round(mx, 5)))
            except Exception as e:
                print("[bootstrap] spectrum sample err:", e)
    except Exception as e:
        print("[bootstrap] error:", e)
    finally:
        _AUDIO_BOOTSTRAP_DONE = True


def onFrameStart(frame):
    """Called at the start of every frame. Reads audio_spectrum directly and
    pushes all reactive parameters to the GLSL shader and compositing ops.
    No longer depends on audio_params or audio_reactive_mapper."""

    global _smooth_bass, _smooth_mid, _smooth_high, _prev_bass
    global _burst_decay, _last_onset_frame

    # One-shot audio chain setup (fires once per session)
    if not _AUDIO_BOOTSTRAP_DONE:
        _bootstrap_audio_chain_once()

    # One-shot: force segmentation_mask_reader DAT to reload from disk
    if not _MASK_READER_RELOADED:
        _force_reload_mask_reader_once()

    # One-shot: wire the GLSL uniform name mapping on fire_aura_glsl.
    if not _UNIFORMS_WIRED:
        _wire_glsl_uniforms_once()

    # One-shot render-pipeline diagnostic (fires once per reload)
    if not _RENDER_DIAG_DONE:
        _diag_render_chain_once()

    # Re-fire render diag every 10 seconds
    if frame % 600 == 0 and frame > 0:
        globals()["_RENDER_DIAG_DONE"] = False
        _diag_render_chain_once()

    # ================================================================
    # DIRECT AUDIO COMPUTATION from audio_spectrum (no audio_params)
    # ================================================================
    asp = op("audio_spectrum")
    if asp is not None and asp.numSamples > 0:
        # Raw per-band energies
        bass_raw = _band_energy(asp, *BASS_BINS)
        mid_raw = _band_energy(asp, *MID_BINS)
        high_raw = _band_energy(asp, *HIGH_BINS)

        # Exponential smoothing
        _smooth_bass = _smooth_bass * BASS_SMOOTH_COEF + bass_raw * (
            1.0 - BASS_SMOOTH_COEF
        )
        _smooth_mid = _smooth_mid * MID_SMOOTH_COEF + mid_raw * (1.0 - MID_SMOOTH_COEF)
        _smooth_high = _smooth_high * HIGH_SMOOTH_COEF + high_raw * (
            1.0 - HIGH_SMOOTH_COEF
        )

        # Onset detection (bass transient)
        bass_delta = bass_raw - _prev_bass
        current_frame = int(frame)
        cooldown_frames = max(1, int(ONSET_COOLDOWN_MS / 1000.0 * 60))
        if (
            bass_delta > ONSET_THRESHOLD
            and (current_frame - _last_onset_frame) > cooldown_frames
        ):
            _burst_decay = 1.0
            _last_onset_frame = current_frame
        _burst_decay *= ONSET_DECAY_RATE
        _prev_bass = bass_raw

    # Clamp to finite
    def _safe(v, lo, hi, default=0.0):
        if not math.isfinite(v):
            return default
        return max(lo, min(hi, v))

    b = _smooth_bass
    m = _smooth_mid
    h = _smooth_high

    flame_intensity = _safe(b * FLAME_INTENSITY_MULT, 0.0, 2.0, 0.05)
    turbulence = _safe(m * TURBULENCE_MULT, 0.0, 1.0, 0.1)
    distortion = _safe(m * DISTORTION_MULT, 0.0, 0.5, 0.05)
    sparkle = _safe(h * SPARKLE_MULT, 0.0, 1.0, 0.0)
    bloom_intensity = _safe(0.2 + h * BLOOM_MULT, 0.0, 3.0, 0.2)
    burst_decay = _safe(_burst_decay, 0.0, 1.0, 0.0)
    bass_smooth = _safe(_smooth_bass, 0.0, 1.0, 0.0)
    mid_smooth = _safe(_smooth_mid, 0.0, 1.0, 0.0)
    high_smooth = _safe(_smooth_high, 0.0, 1.0, 0.0)

    # ---- Periodic audio diagnostic (every 2 seconds at 60fps) ----
    if frame % 120 == 0:
        print(
            "[audio-direct] bass="
            + str(round(b, 6))
            + " mid="
            + str(round(m, 6))
            + " high="
            + str(round(h, 6))
            + " | flame="
            + str(round(flame_intensity, 4))
            + " sparkle="
            + str(round(sparkle, 4))
            + " burst="
            + str(round(burst_decay, 4))
        )

    # ---- Gather body data ----
    bc = op("body_channels")
    try:
        motion_energy = float(bc["motion_energy"]) if bc is not None else 0.0
    except Exception:
        motion_energy = 0.0

    # Normalize motion (raw is 0-100+)
    motion_norm = min(motion_energy / 50.0, 1.0)

    # ---- Update Noise Embers TOP (TD 2022 workaround for particles) ----
    nemb = op("noise_embers")
    if nemb is not None:
        try:
            # Modulate noise speed/amplitude with audio energy
            nemb.par.amp = 0.3 + flame_intensity * 0.7
            nemb.par.rough = 0.4 + turbulence * 0.4
        except Exception:
            pass

    # ---- Update GLSL Shader Uniforms ----
    glsl = op("fire_aura_glsl")
    if glsl is not None:
        # Time is automatic via iTime uniform, but we push custom uniforms
        try:
            # 0-INDEXED value pars: value0x..value8x map to uniname0..8.
            # (Was value1x..value9x — an off-by-one that wrote every band one
            # slot high. uTime = uniname9/value9x stays shader-driven.)
            glsl.par.value0x = flame_intensity  # uFlameIntensity (uniname0)
            glsl.par.value1x = turbulence  # uTurbulence    (uniname1)
            glsl.par.value2x = distortion  # uDistortion    (uniname2)
            glsl.par.value3x = sparkle  # uSparkle       (uniname3)
            glsl.par.value4x = motion_norm  # uMotionEnergy  (uniname4)
            glsl.par.value5x = bass_smooth  # uBassEnergy    (uniname5)
            glsl.par.value6x = mid_smooth  # uMidEnergy     (uniname6)
            glsl.par.value7x = high_smooth  # uHighEnergy    (uniname7)
            glsl.par.value8x = burst_decay  # uBurstDecay    (uniname8)
        except Exception:
            pass

    # ---- Write back to audio_params Constant CHOP (for monitoring/debugging) ----
    ap = op("audio_params")
    if ap is not None:

        def _ap_set(name, value):
            try:
                for i in range(ap.numChans):
                    if ap[i].name == name:
                        ap.par["value" + str(i)] = value
                        return
            except Exception:
                pass

        _ap_set("bass_smooth", bass_smooth)
        _ap_set("mid_smooth", mid_smooth)
        _ap_set("high_smooth", high_smooth)
        _ap_set("flame_intensity", flame_intensity)
        _ap_set("turbulence", turbulence)
        _ap_set("distortion", distortion)
        _ap_set("sparkle", sparkle)
        _ap_set("bloom_intensity", bloom_intensity)
        _ap_set("burst_decay", burst_decay)

    # ---- Update Bloom (blur-based glow, TD 2022 workaround) ----
    bloom_b = op("bloom_blur")
    if bloom_b is not None:
        try:
            bloom_b.par.size = 6.0 + bloom_intensity * 18.0
        except Exception:
            pass
    bloom_comp = op("bloom_post")
    if bloom_comp is not None:
        try:
            bloom_comp.par.opacity2 = 0.2 + bloom_intensity * 0.3
        except Exception:
            pass

    # ---- Update Composite Blend ----
    comp = op("final_composite")
    if comp is not None:
        # Aura opacity: base + boost from audio energy
        aura_alpha = min(0.4 + flame_intensity * 0.3 + motion_norm * 0.2, 1.0)
        try:
            comp.par.opacity2 = aura_alpha
        except Exception:
            pass

    # ---- Burst flash (quick white flash on onset) ----
    flash = op("burst_flash")
    if flash is not None:
        try:
            flash.par.colorr = 1.0
            flash.par.colorg = 0.95
            flash.par.colorb = 0.8
            flash.par.colora = burst_decay * 0.6
        except Exception:
            pass


def onPlayStateChange(state):
    return


def onFrameEnd(frame):
    return


def onCreate():
    print("[aura_compositor] Pipeline controller active")


def onExit():
    print("[aura_compositor] Pipeline controller stopped")
