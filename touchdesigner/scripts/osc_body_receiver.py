# osc_body_receiver.py — CHOP Execute DAT
# =========================================
# Receives /movement/* OSC data from body_mask_sender / movement_tracker
# and routes it into TouchDesigner CHOP channels for the aura pipeline.
#
# SETUP IN TOUCHDESIGNER:
#   1. Create OSC In CHOP  →  name: "osc_body"
#      - Port: 7000
#      - Inputs Filter: /movement/*
#   2. Create CHOP Execute DAT  →  name: "osc_body_receiver"
#      - Paste this script
#      - CHOPs parameter: op('osc_body')
#      - Active: ON
#   3. Create Constant CHOP  →  name: "body_channels"
#      - Channels: lh_x lh_y rh_x rh_y lh_height rh_height
#                  hand_spread body_height head_x head_y shoulder_tilt
#                  motion_energy tracking_active mask_active num_people
# =========================================

def onValueChange(channel, sampleIndex, val, prev):
    """Route incoming /movement/* OSC values into body_channels Constant CHOP."""

    name = channel.name

    # Target Constant CHOP that feeds the aura pipeline
    body = op('body_channels')
    if body is None:
        return

    # --- Person 1 landmark channels ---
    mapping = {
        'movement/person1/left_hand_x':    'lh_x',
        'movement/person1/left_hand_y':    'lh_y',
        'movement/person1/right_hand_x':   'rh_x',
        'movement/person1/right_hand_y':   'rh_y',
        'movement/person1/left_hand_height':  'lh_height',
        'movement/person1/right_hand_height': 'rh_height',
        'movement/person1/hand_spread':    'hand_spread',
        'movement/person1/body_height':    'body_height',
        'movement/person1/head_x':         'head_x',
        'movement/person1/head_y':         'head_y',
        'movement/person1/shoulder_tilt':  'shoulder_tilt',
        'movement/person1/motion_energy':  'motion_energy',
        'movement/person1/tracking_active': 'tracking_active',
        'movement/mask_active':            'mask_active',
        'movement/num_people':             'num_people',
    }

    # Also accept the alternate OSC format from body_mask_sender.py
    alt_mapping = {
        'movement/person1/hand/left/x':      'lh_x',
        'movement/person1/hand/left/y':      'lh_y',
        'movement/person1/hand/right/x':     'rh_x',
        'movement/person1/hand/right/y':     'rh_y',
        'movement/person1/hand/left/height':  'lh_height',
        'movement/person1/hand/right/height': 'rh_height',
        'movement/person1/motion/energy':     'motion_energy',
    }

    # Normalize channel name (remove leading slash)
    clean = name.lstrip('/')

    target = mapping.get(clean) or alt_mapping.get(clean)
    if target is None:
        return

    # Write into the Constant CHOP channel
    try:
        idx = body.chanIndex(target)
        if idx >= 0:
            body.par['value' + str(idx)] = val
    except Exception:
        pass


def whileOn(channel, sampleIndex, val, prev):
    return

def whileOff(channel, sampleIndex, val, prev):
    return

def onOffToOn(channel, sampleIndex, val, prev):
    return

def onOnToOff(channel, sampleIndex, val, prev):
    return
