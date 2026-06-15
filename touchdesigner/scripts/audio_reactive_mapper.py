# audio_reactive_mapper.py — CHOP Execute DAT / Script CHOP
# =============================================================
# Maps Audio Analysis TOP frequency bands to visual parameters
# that drive the fire aura particle system and GLSL shader.
#
# Frequency band mapping:
#   Bass  (20-200 Hz)   → flame intensity, particle size, emission rate
#   Mids  (200-2000 Hz) → turbulence, velocity, distortion
#   Highs (2k-20k Hz)   → sparkle density, bloom intensity
#   Onset detection      → burst triggers (particle explosion + flash)
#
# SETUP IN TOUCHDESIGNER:
#   1. Create Audio Device In CHOP  →  name: "audio_in"
#      - Driver: CoreAudio (macOS) or DirectSound (Windows)
#      - Device: your DJ audio interface / Loopback
#      - Sample Rate: 44100 or 48000
#
#   2. Create Audio Spectrum CHOP  →  name: "audio_spectrum"
#      - Input: audio_in
#      - Output: Magnitude
#      - FFT Size: 2048
#
#   3. Create Constant CHOP  →  name: "audio_params"
#      - Channels:
#          bass_energy  bass_smooth
#          mid_energy   mid_smooth
#          high_energy  high_smooth
#          onset        onset_trigger
#          flame_intensity  particle_size  emission_rate
#          turbulence  velocity  distortion
#          sparkle  bloom_intensity
#          burst_active  burst_decay
#
#   4. Create CHOP Execute DAT  →  name: "audio_reactive_mapper"
#      - Paste this script
#      - CHOPs: op('audio_spectrum')
#      - Active: ON
#
#   ALTERNATIVE: Use as Script CHOP for frame-rate processing.
# =============================================================

import math
print('[LOAD-MARKER-V3] audio_reactive_mapper.py module loaded at absTime.frame=' + str(absTime.frame))

# ---- ONE-SHOT AUDIO CHAIN BOOTSTRAP ----
# Runs on every reload of this file. Idempotent: only writes changed values.
# This is a workaround for TD's textport being unreliable for programmatic input.
# It ensures audio_in is pointed at the PreSonus Studio 1824c (the OBS audio
# source that has the Pioneer mixer going through it) and that the chain is
# active and cooking.
def _bootstrap_audio_chain():
    try:
        ai  = op('/project1/audio_in')
        asp = op('/project1/audio_spectrum')
        arm = op('/project1/audio_reactive_mapper')
        if ai is None:
            print('[bootstrap] audio_in not found')
            return

        # 1. Driver: prefer Core Audio on macOS
        drv_labels = list(ai.par.driver.menuLabels or [])
        drv_names  = list(ai.par.driver.menuNames  or [])
        current_drv = ai.par.driver.val
        for kw in ('core audio', 'coreaudio', 'core'):
            hit = None
            for lab, nm in zip(drv_labels, drv_names):
                if kw in (lab or '').lower() or kw in (nm or '').lower():
                    hit = nm
                    break
            if hit:
                if current_drv != hit:
                    ai.par.driver = hit
                    print('[bootstrap] driver ->', hit)
                break

        # Force cook so device menu refreshes under the new driver
        ai.cook(force=True)

        # 2. Device: prefer 1824c (OBS's capture device), then PreSonus, then BlackHole, then built-in
        DEVICE_PRIORITIES = [
            '1824c', '1824', 'studio 1824',
            'presonus', 'djm-250', 'djm',
            'blackhole', 'loopback',
            'built-in', 'built in', 'macbook',
        ]
        dev_labels = list(ai.par.device.menuLabels or [])
        dev_names  = list(ai.par.device.menuNames  or [])
        current_dev = ai.par.device.val
        for kw in DEVICE_PRIORITIES:
            hit = None
            for lab, nm in zip(dev_labels, dev_names):
                if kw in (lab or '').lower() or kw in (nm or '').lower():
                    hit = nm
                    break
            if hit:
                if current_dev != hit:
                    ai.par.device = hit
                    print('[bootstrap] device ->', hit)
                break

        # 3. Activate + cook
        if not ai.par.active.val:
            ai.par.active = True
            print('[bootstrap] audio_in.active = True')
        ai.cook(force=True)

        # 4. Spectrum cook
        if asp is not None:
            asp.cook(force=True)

        # 5. Mapper: watch spectrum, fire onValueChange, activate
        if arm is not None:
            if arm.par.chop.val != 'audio_spectrum':
                arm.par.chop = 'audio_spectrum'
            if not arm.par.valuechange.val:
                arm.par.valuechange = True
            if not arm.par.active.val:
                arm.par.active = True

        # 6. Report
        errs = ai.errors() or ''
        warns = ai.warnings() or ''
        print('[bootstrap] audio_in:', 'driver=' + ai.par.driver.val,
              '| device=' + ai.par.device.val,
              '| active=' + str(ai.par.active.val),
              ('| ERR=' + errs) if errs else '',
              ('| WARN=' + warns) if warns else '')
        if asp is not None:
            try:
                c0 = asp[0]
                if c0 is not None and len(c0) > 0:
                    mx = max(abs(c0[i]) for i in range(len(c0)))
                    print('[bootstrap] audio_spectrum max bin:', round(mx, 5))
            except Exception as e:
                print('[bootstrap] spectrum sample err:', e)
    except Exception as e:
        print('[bootstrap] error:', e)

# Run setup immediately on every load of this module.
_bootstrap_audio_chain()


# ---- RENDER CHAIN DIAGNOSTIC (runs on each module reload) ----
# Writes output to /tmp/td_render_diag.txt so we can read it back outside TD.
_DIAG_OUT_PATH = '/Users/thomasadair/projects/touchdesigner-dj-suite/td_render_diag.txt'
_DIAG_LINES = []

def _dp(msg):
    _DIAG_LINES.append(str(msg))
    print(str(msg))

def _diag_render_chain():
    global _DIAG_LINES
    _DIAG_LINES = []
    chain = [
        'body_mask_top', 'edge_detect', 'edge_blur',
        'noise_embers',
        'motion_energy_top', 'audio_energy_top',
        'fire_aura_shader_code',
        'fire_aura_glsl',
        'flame_layers',
        'bloom_blur',
        'bloom_post',
        'burst_flash',
        'camera_in',
        'final_composite',
        'output',
    ]
    _dp('\n[rdiag] === RENDER CHAIN === ts=' + str(absTime.frame))
    for n in chain:
        o = op('/project1/' + n)
        if o is None:
            _dp('[rdiag] ' + n + ': MISSING')
            continue
        try:
            errs = (o.errors() or '').strip()
        except Exception:
            errs = ''
        try:
            w = o.width; h = o.height
        except Exception:
            w = h = '?'
        try:
            ins = []
            for i, ic in enumerate(o.inputConnectors):
                src = '-'
                try:
                    if ic.connections:
                        src = ic.connections[0].owner.name
                except Exception:
                    pass
                ins.append(str(i) + '=' + src)
            inputs_s = ','.join(ins) if ins else 'none'
        except Exception:
            inputs_s = '?'
        try:
            bypass = bool(o.par.bypass.val) if hasattr(o.par, 'bypass') else False
        except Exception:
            bypass = False
        _dp('[rdiag] ' + n +
            ' res=' + str(w) + 'x' + str(h) +
            ' in=' + inputs_s +
            ' bypass=' + str(bypass) +
            (' ERR=' + errs[:60] if errs else ''))

    # Find syphon/spout ops
    _dp('[rdiag] --- syphon/spout search ---')
    root = op('/project1')
    if root is not None:
        found = 0
        for child in root.children:
            tname = (child.OPType or '').lower()
            nm = (child.name or '').lower()
            if 'syphon' in tname or 'syphon' in nm or 'spout' in tname or 'spout' in nm:
                found += 1
                try:
                    e = (child.errors() or '').strip()
                except Exception:
                    e = ''
                src = 'NOTHING'
                try:
                    if child.inputConnectors and child.inputConnectors[0].connections:
                        src = child.inputConnectors[0].connections[0].owner.path
                except Exception:
                    src = '<err>'
                pars = {}
                for pn in ('active', 'sendername', 'senderName'):
                    try:
                        if hasattr(child.par, pn):
                            pars[pn] = getattr(child.par, pn).val
                    except Exception:
                        pass
                _dp('[rdiag] ' + child.path + ' type=' + child.OPType +
                    ' in0<-' + src + ' pars=' + str(pars) +
                    (' ERR=' + e[:80] if e else ''))
        if found == 0:
            _dp('[rdiag] NO syphon/spout ops found')

    # All errored ops under /project1
    _dp('[rdiag] --- errored ops ---')
    bad = 0
    if root is not None:
        for child in root.children:
            try:
                e = (child.errors() or '').strip()
                if e:
                    bad += 1
                    _dp('[rdiag]   ' + child.path + ': ' + e[:120])
            except Exception:
                pass
    _dp('[rdiag] errored count: ' + str(bad))

    # Also dump audio_params values so we know why mapper isn't writing
    ap = op('/project1/audio_params')
    if ap is not None:
        vals = {}
        for i in range(ap.numChans):
            try:
                vals[ap[i].name] = round(float(ap[i][0]), 5)
            except Exception:
                pass
        _dp('[rdiag] audio_params values: ' + str(vals))

    # Also dump audio_reactive_mapper DAT parameters
    arm = op('/project1/audio_reactive_mapper')
    if arm is not None:
        pars = {}
        for pn in ('chop', 'active', 'valuechange', 'onoffton', 'offtoon', 'whileon', 'whileoff'):
            try:
                if hasattr(arm.par, pn):
                    pars[pn] = getattr(arm.par, pn).val
            except Exception:
                pass
        _dp('[rdiag] audio_reactive_mapper pars: ' + str(pars))

    _dp('[rdiag] === END ===\n')

    # Write to file so we can read it back from outside TD
    try:
        with open(_DIAG_OUT_PATH, 'w') as f:
            f.write('\n'.join(_DIAG_LINES))
        print('[rdiag] wrote diagnostic to ' + _DIAG_OUT_PATH)
    except Exception as e:
        print('[rdiag] write err:', e)

try:
    _diag_render_chain()
except Exception as e:
    print('[rdiag] fatal:', e)


# ---- Tunable parameters ----
# Frequency bin ranges (indices into audio_spectrum CHOP samples)
# TD's Audio Spectrum CHOP outputs ~22050 samples covering 0–22050 Hz
# i.e. ~1 Hz per bin regardless of FFT size setting.
# Bass: bins 20-200   (20–200 Hz)
# Mids: bins 200-2000 (200–2000 Hz)
# Highs: bins 2000-20000 (2–20 kHz)
BASS_BINS  = (20, 200)
MID_BINS   = (200, 2000)
HIGH_BINS  = (2000, 20000)

# Smoothing (0 = no smoothing, 0.99 = very smooth)
BASS_SMOOTH  = 0.85
MID_SMOOTH   = 0.80
HIGH_SMOOTH  = 0.75

# Onset detection
ONSET_THRESHOLD    = 0.00005  # Minimum energy jump to trigger (spectrum magnitudes are small ~0.0001 scale)
ONSET_COOLDOWN_MS  = 120    # Minimum ms between triggers
ONSET_DECAY_RATE   = 0.92   # How fast burst decays per frame

# Output scaling — spectrum magnitudes are ~0.0001–0.001 range; scale up aggressively
FLAME_INTENSITY_MULT = 8000.0
PARTICLE_SIZE_MULT   = 6000.0
EMISSION_RATE_MULT   = 5.0
TURBULENCE_MULT      = 6000.0
VELOCITY_MULT        = 8000.0
DISTORTION_MULT      = 4000.0
SPARKLE_MULT         = 10000.0
BLOOM_MULT           = 5000.0

# ---- State ----
_prev_bass = 0.0
_prev_mid  = 0.0
_prev_high = 0.0
_smooth_bass = 0.0
_smooth_mid  = 0.0
_smooth_high = 0.0
_onset_active = 0.0
_burst_decay  = 0.0
_last_onset_frame = -999


def _band_energy(spectrum_chop, lo, hi):
    """Sum energy in a frequency bin range from the spectrum CHOP."""
    if spectrum_chop is None or spectrum_chop.numSamples == 0:
        return 0.0
    n = spectrum_chop.numSamples
    lo = max(0, min(lo, n - 1))
    hi = max(0, min(hi, n - 1))
    total = 0.0
    chan = spectrum_chop[0]  # First channel (mono or left)
    for i in range(lo, hi + 1):
        total += abs(chan[i])
    count = hi - lo + 1
    return total / max(count, 1)


def onValueChange(channel, sampleIndex, val, prev):
    """Called when audio spectrum updates."""
    global _prev_bass, _prev_mid, _prev_high
    global _smooth_bass, _smooth_mid, _smooth_high
    global _onset_active, _burst_decay, _last_onset_frame

    spectrum = op('audio_spectrum')
    params = op('audio_params')
    if params is None:
        return

    # ---- Compute band energies ----
    bass_raw  = _band_energy(spectrum, *BASS_BINS)
    mid_raw   = _band_energy(spectrum, *MID_BINS)
    high_raw  = _band_energy(spectrum, *HIGH_BINS)

    # ---- Smooth ----
    _smooth_bass = _smooth_bass * BASS_SMOOTH + bass_raw * (1.0 - BASS_SMOOTH)
    _smooth_mid  = _smooth_mid  * MID_SMOOTH  + mid_raw  * (1.0 - MID_SMOOTH)
    _smooth_high = _smooth_high * HIGH_SMOOTH + high_raw * (1.0 - HIGH_SMOOTH)

    # ---- Onset detection (bass transient) ----
    bass_delta = bass_raw - _prev_bass
    current_frame = absTime.frame
    frames_since_onset = current_frame - _last_onset_frame
    cooldown_frames = max(1, int(ONSET_COOLDOWN_MS / 1000.0 * 60))

    if bass_delta > ONSET_THRESHOLD and frames_since_onset > cooldown_frames:
        _onset_active = 1.0
        _burst_decay = 1.0
        _last_onset_frame = current_frame
    else:
        _onset_active = 0.0

    # Decay burst
    _burst_decay *= ONSET_DECAY_RATE

    # Store for next frame
    _prev_bass = bass_raw
    _prev_mid  = mid_raw
    _prev_high = high_raw

    # ---- Map to visual parameters ----
    def _set(name, value):
        try:
            idx = params.chanIndex(name)
            if idx >= 0:
                params.par['value' + str(idx)] = value
        except Exception:
            pass

    # Raw energies
    _set('bass_energy',  bass_raw)
    _set('mid_energy',   mid_raw)
    _set('high_energy',  high_raw)
    _set('bass_smooth',  _smooth_bass)
    _set('mid_smooth',   _smooth_mid)
    _set('high_smooth',  _smooth_high)

    # Onset
    _set('onset',         _onset_active)
    _set('onset_trigger', _onset_active)

    # ---- BASS → Flame intensity, particle size, emission rate ----
    b = _smooth_bass
    _set('flame_intensity', b * FLAME_INTENSITY_MULT)
    _set('particle_size',   0.3 + b * PARTICLE_SIZE_MULT)
    _set('emission_rate',   100 + b * EMISSION_RATE_MULT * 1000)

    # ---- MIDS → Turbulence, velocity, distortion ----
    m = _smooth_mid
    _set('turbulence',  m * TURBULENCE_MULT)
    _set('velocity',    0.5 + m * VELOCITY_MULT)
    _set('distortion',  m * DISTORTION_MULT)

    # ---- HIGHS → Sparkle, bloom ----
    h = _smooth_high
    _set('sparkle',         h * SPARKLE_MULT)
    _set('bloom_intensity', 0.2 + h * BLOOM_MULT)

    # ---- ONSET → Burst ----
    _set('burst_active', _onset_active)
    _set('burst_decay',  _burst_decay)


def whileOn(channel, sampleIndex, val, prev):
    return

def whileOff(channel, sampleIndex, val, prev):
    return

def onOffToOn(channel, sampleIndex, val, prev):
    return

def onOnToOff(channel, sampleIndex, val, prev):
    return
