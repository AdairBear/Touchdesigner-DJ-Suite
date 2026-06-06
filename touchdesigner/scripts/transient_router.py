# transient_router.py — CHOP Execute DAT
# Paste into a CHOP Execute DAT. Set CHOPs = your beat detection output Null CHOP.
# Expects channels: kick_onset (0/1), snare_onset (0/1), bass_rms (0.0-1.0)
#
# Routes audio transients to geometry operators:
#   Kick  → Twist SOP  (op('twist1').par.strength)   — macro distortions on drops
#   Snare → Noise TOP  (op('noise1').par.tz)          — Z-translate noise shift on snare
#   Bass  → LFO CHOP   (op('lfo1').par.rate)          — continuous rate modulation

import td

# ─── TUNING CONSTANTS ────────────────────────────────────────────────────────
KICK_STRENGTH_BASE   = 0.3    # Twist resting state
KICK_STRENGTH_PEAK   = 2.0    # Twist on kick hit
KICK_DECAY_FRAMES    = 6      # Frames to decay back to base (~0.1s at 60fps)

SNARE_TZ_BASE        = 0.0    # Noise TOP Z base
SNARE_TZ_BURST       = 0.3    # Noise TOP Z on snare hit
SNARE_DECAY_FRAMES   = 8      # Frames to decay

BASS_RATE_MIN        = 0.3    # LFO rate at silence
BASS_RATE_MAX        = 2.0    # LFO rate at full reese

# Internal state
_kick_frames_remaining  = 0
_snare_frames_remaining = 0

def onValueChange(channel, sampleIndex, val, prev):
    global _kick_frames_remaining, _snare_frames_remaining
    name = channel.name

    # ── KICK → Twist SOP strength ──────────────────────────────────────────
    if name == 'kick_onset' and val > 0.5:
        twist = op('twist1')
        if twist:
            twist.par.strength = KICK_STRENGTH_PEAK
            _kick_frames_remaining = KICK_DECAY_FRAMES
            print(f'[transient] KICK → twist.strength={KICK_STRENGTH_PEAK}')
        else:
            print('[transient] WARNING: op(twist1) not found')

    # ── SNARE → Noise TOP translate Z ──────────────────────────────────────
    elif name == 'snare_onset' and val > 0.5:
        noise = op('noise1')
        if noise:
            base_tz = absTime.seconds * 0.5
            noise.par.tz = base_tz + SNARE_TZ_BURST
            _snare_frames_remaining = SNARE_DECAY_FRAMES
            print(f'[transient] SNARE → noise.tz={noise.par.tz.val:.3f}')
        else:
            print('[transient] WARNING: op(noise1) not found')

    # ── BASS → LFO CHOP rate (continuous) ──────────────────────────────────
    elif name == 'bass_rms':
        lfo = op('lfo1')
        if lfo:
            rate = BASS_RATE_MIN + val * (BASS_RATE_MAX - BASS_RATE_MIN)
            lfo.par.rate = rate

def whileOn(channel, sampleIndex, val, prev):
    pass

def whileOff(channel, sampleIndex, val, prev):
    pass

def onOffToOn(channel, sampleIndex, val, prev):
    pass

def onOnToOff(channel, sampleIndex, val, prev):
    pass

# ─── DECAY HANDLER ───────────────────────────────────────────────────────────
# Paste this into a separate Execute DAT set to "Frame Start" to handle decay.
# Or add to your existing frame-start DAT:
#
#   def onFrameStart(frame):
#       import TDStoreTools
#       # Kick decay
#       if _kick_frames_remaining > 0:
#           _kick_frames_remaining -= 1
#           t = _kick_frames_remaining / KICK_DECAY_FRAMES
#           strength = KICK_STRENGTH_BASE + t * (KICK_STRENGTH_PEAK - KICK_STRENGTH_BASE)
#           twist = op('twist1')
#           if twist: twist.par.strength = strength
#       # Snare decay
#       if _snare_frames_remaining > 0:
#           _snare_frames_remaining -= 1
#           noise = op('noise1')
#           if noise:
#               base_tz = absTime.seconds * 0.5
#               noise.par.tz = base_tz
