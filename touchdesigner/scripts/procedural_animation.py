# procedural_animation.py — CHOP Execute DAT + Frame Execute DAT
# Three simultaneous modulation layers running at all times.
# Paste the relevant sections into the appropriate DATs.
#
# THE SWELL  : LFO CHOP → Geometry Scale (0.85–1.15), driven by bass_rms
# THE PULSE  : Noise SOP → Geometry Position, organic drift via absTime.seconds
# THE FLIP   : kick_onset > 0.8 → toggle Geometry Rotate Y (0° ↔ 180°)

# ─── CONSTANTS ───────────────────────────────────────────────────────────────
SWELL_SCALE_MIN  = 0.85
SWELL_SCALE_MAX  = 1.15
PULSE_AMP_MIN    = 0.02
PULSE_AMP_MAX    = 0.08
FLIP_THRESHOLD   = 0.80   # kick_onset must exceed this for a flip
FLIP_COOLDOWN_F  = 20     # frames minimum between flips (~0.33s at 60fps)

# State
_flip_state          = 0       # 0 = 0°, 1 = 180°
_flip_cooldown_remaining = 0

# ─── CHOP EXECUTE DAT ────────────────────────────────────────────────────────
# Set CHOPs = your beat/OSC Null CHOP

def onValueChange(channel, sampleIndex, val, prev):
    global _flip_state, _flip_cooldown_remaining
    name = channel.name

    # ── THE SWELL: bass_rms drives LFO rate → Geometry scale ─────────────
    # The LFO CHOP (lfo_swell) handles the actual oscillation.
    # This just updates its rate from bass_rms.
    if name == 'bass_rms':
        lfo = op('lfo_swell')
        if lfo:
            # Map bass_rms (0-1) to LFO rate (0.3–1.5 Hz for organic breathing)
            rate = 0.3 + val * 1.2
            lfo.par.rate = rate
        # Also update Geometry scale amplitude directly
        geo = op('geo_aura') or op('geo1')
        if geo:
            amp = PULSE_AMP_MIN + val * (PULSE_AMP_MAX - PULSE_AMP_MIN)
            # Noise amplitude on SOP drives pulse depth
            noise_sop = op('noise_pulse')
            if noise_sop:
                noise_sop.par.amp = amp

    # ── THE FLIP: heavy kick → toggle Rotate Y ───────────────────────────
    elif name == 'kick_onset' and val > FLIP_THRESHOLD:
        if _flip_cooldown_remaining <= 0:
            _flip_state = 1 - _flip_state
            rotate_y = 180.0 if _flip_state else 0.0
            geo = op('geo_aura') or op('geo1')
            if geo:
                geo.par.ry = rotate_y
                print(f'[flip] Rotate Y → {rotate_y}° (kick={val:.2f})')
            _flip_cooldown_remaining = FLIP_COOLDOWN_F

def whileOn(channel, sampleIndex, val, prev):
    pass

def whileOff(channel, sampleIndex, val, prev):
    pass

def onOffToOn(channel, sampleIndex, val, prev):
    pass

def onOnToOff(channel, sampleIndex, val, prev):
    pass


# ─── FRAME EXECUTE DAT (separate DAT, Frame Start checked) ───────────────────
# Name: procedural_frame_exec
# This handles The Swell scale output and cooldown decrement.
# Also drives The Pulse via absTime so it never repeats.

def onFrameStart(frame):
    global _flip_cooldown_remaining

    # Cooldown tick
    if _flip_cooldown_remaining > 0:
        _flip_cooldown_remaining -= 1

    # ── THE SWELL: read LFO CHOP and apply to Geometry scale ─────────────
    lfo = op('lfo_swell')
    geo = op('geo_aura') or op('geo1')
    if lfo and geo:
        # LFO outputs -1..1, remap to SWELL_SCALE_MIN..SWELL_SCALE_MAX
        lfo_val = lfo['chan1'].eval() if lfo.numChans > 0 else 0.0
        scale = SWELL_SCALE_MIN + (lfo_val + 1.0) * 0.5 * (SWELL_SCALE_MAX - SWELL_SCALE_MIN)
        geo.par.sx = scale
        geo.par.sy = scale
        geo.par.sz = scale

    # ── THE PULSE: absTime-seeded noise for organic position drift ────────
    if geo:
        t = absTime.seconds
        # Three offset time seeds for X/Y/Z independence
        import math
        dx = math.sin(t * 0.7 + 1.0) * 0.04 + math.sin(t * 1.3) * 0.02
        dy = math.sin(t * 0.5 + 2.1) * 0.03 + math.sin(t * 0.9) * 0.015
        dz = math.sin(t * 0.6 + 3.7) * 0.025

        geo.par.tx = dx
        geo.par.ty = dy
        geo.par.tz = dz
