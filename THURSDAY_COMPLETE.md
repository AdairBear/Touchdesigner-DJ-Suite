# Thursday Scripting Session — Complete
**Date:** 2026-04-23
**Session:** Pre-testing script writing for TouchDesigner DJ Suite

All files written to `/Users/thomasadair/projects/touchdesigner-dj-suite/`

---

## Deliverables

| File | Description | Status |
|------|-------------|--------|
| `fix_venv.sh` | Rebuilds corrupted venv with hardcoded paths from deleted duplicate folder | ✅ |
| `touchdesigner/scripts/chop_normalizer.py` | CHOP Execute DAT — normalizes MediaPipe raw (-0.3→1.2) to 0.0–1.0, stores values via parent().store() | ✅ |
| `touchdesigner/scripts/beat_detector_setup.py` | Script DAT — configures madmomTD (primary) or AudioAnalyze CHOP (fallback) for 150–180 BPM Jungle detection | ✅ |
| `touchdesigner/scripts/transient_router.py` | CHOP Execute DAT — routes kick→Twist SOP, snare→Noise TOP, bass→LFO rate, with exponential decay | ✅ |
| `touchdesigner/scripts/procedural_animation.py` | CHOP Execute + Frame Execute DATs — The Swell (scale 0.85–1.15), The Pulse (absTime drift), The Flip (180° on heavy kick) | ✅ |
| `touchdesigner/scripts/geometry_instancing_pipeline.py` | Script DAT verifier — checks Tube SOP → Twist → SOP to CHOP → CHOP to TOP → Geometry COMP chain, flags critical CHOP to TOP settings | ✅ |
| `touchdesigner/scripts/obs_websocket_td.py` | CHOP Execute DAT — auto scene switch on sustained heavy kick, 8s cooldown, TD-OBSWebSocket tox integration | ✅ |
| `touchdesigner/scripts/diagnose_obs_double_image.py` | Terminal Python script — connects to OBS via WebSocket, finds duplicate Syphon/NDI/Spout sources causing double-image | ✅ |
| `FRIDAY_TESTING_GUIDE.md` | Full step-by-step Friday checklist with pass/fail criteria and troubleshooting | ✅ |
| `THURSDAY_COMPLETE.md` | This file | ✅ |

---

## Key Technical Notes for Friday

**Most likely issue: OBS double-image**
Run `diagnose_obs_double_image.py` first — it's the fastest to fix and blocks everything downstream.
Cause is almost certainly a duplicate Syphon Out TOP in the TD network.

**CHOP to TOP critical settings** (will silently produce wrong instancing if wrong):
- Data Format = **RGB** (not RGBA, not float32)
- Image Layout = **Fit to Square**

**Beat detection at 180 BPM:**
madmomTD is the right tool. Amplitude threshold (AudioAnalyze) will miss ghost notes and syncopated breaks.
Install: github.com/ioannismihailidis/madmomTD — drag .tox into network.

**If TD is slow:**
F1 = Perform Mode. Always test performance in Perform Mode, not the editor.
The 1000×1000 Tube SOP cook takes 2–3s on first load — expected, then stays fast.

**Audio chain already confirmed working** (from Apr 19 session):
PreSonus Studio 1824c → AudioAnalyze CHOP → fire aura uniforms. Don't redo the bootstrap.
Pick up from where the audio_params were confirmed with real values.

---

## What's Already Working (Don't Touch)

- Audio chain bootstrap (`aura_compositor.py`) — PreSonus 1824c auto-detected ✓
- Fire aura GLSL shader — 10 parameterized uniforms ✓
- OSC body receiver (`osc_body_receiver.py`) — multi-person tracking ✓
- OBS controller (`obs_controller.py`) — scene switching via python ✓
- Movement tracker — MediaPipe → OSC → TD pipeline ✓

---

## Friday Order of Operations

1. Fix venv → 2. OBS double-image fix → 3. CHOP normalization →
4. Beat detection → 5. Transient routing → 6. Geometry instancing →
7. Procedural animation → 8. OBS TD integration → 9. Full system test

**Target: system GO by 14:00 Friday.**
