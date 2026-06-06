# beat_detector_setup.py — Script DAT (run once on startup, or paste in Textport)
#
# PURPOSE: Configure beat detection for 150-180 BPM Jungle/Breakbeat.
# Standard amplitude threshold detection FAILS at this tempo because:
#   - Breakbeats have syncopated ghost notes between main hits
#   - At 180 BPM, kicks are 333ms apart — amplitude rings before fully decaying
#   - The "Amen break" has 3-4 hits in the time most detectors expect 1
#
# PRIMARY: madmomTD (ioannismihailidis/madmomTD)
#   AI-based onset detection trained on real drum patterns.
#   Handles syncopation, ghost notes, and tempo ambiguity correctly.
#   Install: download madmomTD.tox from github.com/ioannismihailidis/madmomTD
#            drag into TD network, connect Audio Device In CHOP as input.
#
# FALLBACK: AudioAnalyze CHOP with tight thresholds (configured below)

# ─── OUTPUT CHANNELS (what downstream DATs expect) ───────────────────────────
# kick_onset  : 0.0 or 1.0 — fires on each kick transient
# snare_onset : 0.0 or 1.0 — fires on each snare/rimshot transient
# bass_rms    : 0.0–1.0    — continuous sub-bass energy (reese bassline level)

# ─── FALLBACK: AudioAnalyze CHOP parameters ──────────────────────────────────
# If madmomTD is unavailable, create an AudioAnalyze CHOP and set:
AUDIOANALYZE_PARAMS = {
    'Attack Time':  0.003,   # 3ms — fast enough to catch transients at 180 BPM
    'Release Time': 0.08,    # 80ms — decays before next hit at 333ms intervals
    'Low Freq':     20,      # Hz — sub-bass for kick/reese detection
    'High Freq':    200,     # Hz — keep kick/bass separation clean
}

# Threshold for kick detection in fallback mode
# Set LOWER than default — Jungle kicks are often layered, not always the loudest hit
KICK_THRESHOLD  = 0.55   # Lower than default 0.7 — catches ghost hits too
SNARE_THRESHOLD = 0.45   # Snares in Amen break are often quieter than kick

def setup_beat_detection():
    """
    Call this from a Script DAT or Textport to verify beat detection state.
    Checks for madmomTD first, falls back to AudioAnalyze CHOP config.
    """
    # Check for madmomTD tox
    madmom = op('madmomTD1')
    if madmom:
        print('[beat] madmomTD found — AI beat detection active')
        print('[beat] Expects: kick_onset, snare_onset, bass_rms channels on output')
        print('[beat] At 180 BPM, kick fires every ~333ms. Check Textport for missed beats.')
        return 'madmom'

    # Check for AudioAnalyze CHOP
    aa = op('audioin_analyze') or op('audioanalyze1') or op('audioanalyze')
    if aa:
        print('[beat] AudioAnalyze CHOP found — applying fallback parameters')
        try:
            aa.par.attacktime  = AUDIOANALYZE_PARAMS['Attack Time']
            aa.par.releasetime = AUDIOANALYZE_PARAMS['Release Time']
            aa.par.flow        = AUDIOANALYZE_PARAMS['Low Freq']
            aa.par.fhigh       = AUDIOANALYZE_PARAMS['High Freq']
            print(f'[beat] Attack={aa.par.attacktime.val}s | Release={aa.par.releasetime.val}s')
            print(f'[beat] Freq range: {aa.par.flow.val}–{aa.par.fhigh.val} Hz')
        except Exception as e:
            print(f'[beat] Parameter set failed: {e}')
        print(f'[beat] Kick threshold: {KICK_THRESHOLD} | Snare threshold: {SNARE_THRESHOLD}')
        print('[beat] WARNING: Fallback may miss syncopated ghost notes at 180 BPM')
        return 'audioanalyze'

    print('[beat] ERROR: No beat detection found.')
    print('[beat] Install madmomTD.tox from github.com/ioannismihailidis/madmomTD')
    print('[beat] OR create an AudioAnalyze CHOP named "audioin_analyze"')
    return None

# Run on load
result = setup_beat_detection()
print(f'[beat] Detection mode: {result}')
