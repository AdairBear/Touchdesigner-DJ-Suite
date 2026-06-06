# chop_normalizer.py — CHOP Execute DAT
# Paste into a CHOP Execute DAT. Set CHOPs = your OSC In CHOP (osc_in1, port 7000).
#
# Node chain this script documents:
#   OSC In CHOP (port 7000)
#     → Select CHOP  (pick channels: person*/hand*, motion_energy, body_height, bpm, kick_onset, reese_rms)
#       → Math CHOP  (From Range=-0.3,1.2 | To Range=0.0,1.0 | Clamp=On)  ← do this in TD params, not script
#         → Merge CHOP
#           → Null CHOP  (this DAT watches the Null)
#
# Why: MediaPipe outputs camera-space coords. Hands at top of frame ≈ -0.30, bottom ≈ 1.20.
# The Math CHOP does the heavy lifting via parameters — this script handles per-channel
# overrides and prints diagnostics to Textport.

# Per-channel normalization ranges (in_min, in_max)
CHANNEL_RANGES = {
    # Hand positions — camera space, full vertical range
    'person1_left_hand_y':  (-0.30, 1.20),
    'person1_right_hand_y': (-0.30, 1.20),
    'person2_left_hand_y':  (-0.30, 1.20),
    'person2_right_hand_y': (-0.30, 1.20),
    'person3_left_hand_y':  (-0.30, 1.20),
    'person3_right_hand_y': (-0.30, 1.20),
    'person4_left_hand_y':  (-0.30, 1.20),
    'person4_right_hand_y': (-0.30, 1.20),
    # Hand depth (Z) — less reliable, wider range
    'person1_right_hand_z': (-0.50, 0.50),
    'person1_left_hand_z':  (-0.50, 0.50),
    # Spread / energy — already 0-100 from tracker
    'hand_spread':     (0.0, 100.0),
    'motion_energy':   (0.0, 100.0),
    'body_height':     (0.0, 1.0),
    # Audio channels — already normalized at source
    'bpm':         (140.0, 200.0),   # Jungle tempo range
    'kick_onset':  (0.0, 1.0),
    'reese_rms':   (0.0, 1.0),
    'snare_onset': (0.0, 1.0),
    'bass_rms':    (0.0, 1.0),
}

_diag_frame = 0

def normalize(val, in_min, in_max):
    if in_max == in_min:
        return 0.0
    return max(0.0, min(1.0, (val - in_min) / (in_max - in_min)))

def onValueChange(channel, sampleIndex, val, prev):
    global _diag_frame
    name = channel.name

    if name in CHANNEL_RANGES:
        in_min, in_max = CHANNEL_RANGES[name]
        norm = normalize(val, in_min, in_max)

        # Write normalized value to a storage dict so other DATs can read it
        parent().store(f'norm_{name}', norm)

        # Diagnostic print every 120 frames for key channels
        _diag_frame += 1
        if _diag_frame % 120 == 0 and name in ('kick_onset', 'bass_rms', 'person1_right_hand_y'):
            print(f'[norm] {name}: raw={val:.3f} → norm={norm:.3f}')

def whileOn(channel, sampleIndex, val, prev):
    pass

def whileOff(channel, sampleIndex, val, prev):
    pass

def onOffToOn(channel, sampleIndex, val, prev):
    pass

def onOnToOff(channel, sampleIndex, val, prev):
    pass
