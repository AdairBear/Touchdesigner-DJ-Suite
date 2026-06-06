# Friday Testing Guide — TouchDesigner DJ Suite
**Date:** Friday 2026-04-24, start at 12:00
**Goal:** Wire everything live, run a 5-minute DJ set, confirm all systems go

---

## Pre-Flight (5 min)

- [ ] `cd ~/projects/touchdesigner-dj-suite && ./fix_venv.sh`
- [ ] `source venv/bin/activate`
- [ ] Open **dj_visuals.live_2026-04-19.3.toe** in TouchDesigner
- [ ] Run movement_tracker.py: `python python/movement_tracker.py`
- [ ] In TD Textport (Alt+T): confirm OSC channels arriving on port 7000
  - Look for: `person1_right_hand_y`, `kick_onset`, `bass_rms`
- [ ] OBS open, WebSocket Server enabled (Tools → WebSocket Server Settings)
- [ ] Serato running, audio routing through PreSonus 1824c

---

## Step 1 — OBS Double-Image Fix (do first, OBS is open) (10 min)

- [ ] Run: `python touchdesigner/scripts/diagnose_obs_double_image.py`
- [ ] Fix any flagged duplicate Syphon sources
- [ ] In TD Textport: `print([o.name for o in ops() if 'syphon' in o.name.lower()])`
- [ ] Confirm only ONE Syphon Out TOP exists
- [ ] Check OBS preview — single clean image, no overlay doubling
- [ ] **Pass:** Single clean TD output visible in OBS

---

## Step 2 — CHOP Normalization (10 min)

- [ ] In TD: create a CHOP Execute DAT, paste `touchdesigner/scripts/chop_normalizer.py`
- [ ] Set DAT CHOPs parameter → your OSC In CHOP (port 7000)
- [ ] Confirm Math CHOP parameters: From Range=(-0.3, 1.2) | To Range=(0.0, 1.0) | Clamp=On
- [ ] Stand in front of camera — raise/lower hands
- [ ] In Textport: channels should read 0.0 (hands low) → 1.0 (hands high)
- [ ] No values outside 0.0–1.0 range
- [ ] **Pass:** `person1_right_hand_y` reads 0.0–1.0 across full arm range

---

## Step 3 — Beat Detection (15 min)

- [ ] Play Jungle music through Serato (150–180 BPM)
- [ ] **madmomTD path:** drag `madmomTD.tox` into network, connect Audio Device In CHOP
  - Confirm: `kick_onset` fires 1.0 on every kick hit, returns to 0.0 between
- [ ] **Fallback path:** run `touchdesigner/scripts/beat_detector_setup.py` in Textport
  - Confirm AudioAnalyze CHOP configured with attack=3ms, release=80ms
- [ ] Watch `kick_onset` channel in CHOP viewer while music plays
- [ ] Count: does it fire on every kick? (At 180 BPM expect ~3 fires/second)
- [ ] **Pass:** `kick_onset` triggers reliably on kicks, `bass_rms` moves with reese bassline

---

## Step 4 — Transient Routing (10 min)

- [ ] Create CHOP Execute DAT, paste `touchdesigner/scripts/transient_router.py`
- [ ] Set CHOPs → beat detection Null CHOP
- [ ] Confirm operators exist: `twist1`, `noise1`, `lfo1` (create if missing)
- [ ] Play music:
  - [ ] `twist1.par.strength` jumps on kick hits (watch parameter in TD)
  - [ ] `noise1.par.tz` shifts on snare hits
  - [ ] `lfo1.par.rate` varies continuously with bass (0.3–2.0 Hz)
- [ ] **Pass:** All three respond to music in real-time, no errors in Textport

---

## Step 5 — Geometry Instancing Pipeline (15 min)

- [ ] Run `touchdesigner/scripts/geometry_instancing_pipeline.py` in Textport
- [ ] Fix any ✗ items (missing operators)
- [ ] **CRITICAL check:** CHOP to TOP operator:
  - Data Format = **RGB** (not RGBA)
  - Image Layout = **Fit to Square**
- [ ] Enable Instancing on Geometry COMP
  - Instance Translate X = CHOP_to_TOP:r
  - Instance Translate Y = CHOP_to_TOP:g
  - Instance Translate Z = CHOP_to_TOP:b
- [ ] Expected: initial cook of Tube SOP (1000×1000) takes 2–3 seconds — normal
- [ ] Switch to Perform Mode (F1) for real-time cook
- [ ] **Pass:** Geometry instances appear and Twist deforms on kick hits

---

## Step 6 — Procedural Animation (10 min)

- [ ] Create CHOP Execute DAT, paste `touchdesigner/scripts/procedural_animation.py`
  - (top section — the CHOP Execute part)
- [ ] Create Frame Execute DAT, paste the `onFrameStart` section from the same file
- [ ] With music playing confirm three layers visible:
  - [ ] **The Swell:** geometry slowly scales 0.85–1.15 in time with bass
  - [ ] **The Pulse:** geometry drifts organically — never repeats pattern
  - [ ] **The Flip:** on heavy drop kicks (kick_onset > 0.8), geometry flips 180°
- [ ] Flip cooldown working: no more than one flip every ~0.3s
- [ ] **Pass:** All three layers visible simultaneously, no jitter, no freezing

---

## Step 7 — OBS Integration (10 min)

- [ ] Download TD-OBSWebSocket.tox from github.com/acdvs/TD-OBSWebSocket
- [ ] Drag into TD network, configure: Host=127.0.0.1, Port=4455, Password=(yours)
- [ ] Click Connect — confirm green
- [ ] Create CHOP Execute DAT, paste `touchdesigner/scripts/obs_websocket_td.py`
- [ ] In OBS, create scenes named exactly: `Drop Scene`, `Build Scene`, `Main Scene`
- [ ] Play music with heavy kicks — confirm OBS auto-switches to "Drop Scene" on drops
- [ ] Cooldown working: no rapid scene switching (min 8 seconds between)
- [ ] **Pass:** OBS switches to Drop Scene on heavy kick, recovers cleanly

---

## Step 8 — Full System Test (15 min)

- [ ] All components running simultaneously
- [ ] Run a 5-minute Jungle set at 170–180 BPM
- [ ] Check TD FPS indicator (top-left): must stay above 30 FPS
  - If below 30: switch to Perform Mode (F1) — this is normal for editor
- [ ] CPU usage: `top` in terminal — TD should be under 70% CPU
- [ ] Total latency test: clap hands — fire aura should react within ~2 seconds
- [ ] Body tracking: walk in/out of frame — aura follows body
- [ ] OBS preview: single clean output, audio-reactive fire aura, body-reactive movement
- [ ] Record 30 seconds in OBS, play back — confirm no double-image, no frame drops

---

## If Things Go Wrong

**TD timeline stuck (frame counter not advancing):**
- Switch to Perform Mode (F1) — editor preview is throttled, perform mode is not
- Or: reduce Tube SOP to 500×500 temporarily to lighten cook

**kick_onset not firing:**
- Check AudioAnalyze CHOP freq range (20–200 Hz for kick)
- Lower KICK_THRESHOLD in transient_router.py to 0.4
- Try madmomTD if not already using it

**Double-image persists after OBS fix:**
- In TD Textport: `print([o.name for o in ops('Syphon*')])`
- Delete all but the final output Syphon Out TOP
- Check Over TOP — not compositing twice

**OBS scene switch not triggering:**
- Confirm TD-OBSWebSocket shows green connected state
- Confirm OBS scene names match exactly (case-sensitive)
- Temporarily lower KICK_SCENE_THRESHOLD to 0.7 in obs_websocket_td.py

**Performance too slow:**
- Tube SOP: reduce rows/cols to 500×500
- Disable body segmentation mask (heaviest compute)
- Close all other apps except TD + OBS

---

## Go/No-Go Criteria

| Check | Required |
|-------|----------|
| Single clean OBS output | ✅ Required |
| kick_onset fires reliably | ✅ Required |
| Twist SOP reacts to kicks | ✅ Required |
| Geometry instancing visible | ✅ Required |
| Swell + Pulse running | ✅ Required |
| TD at 30+ FPS in Perform Mode | ✅ Required |
| OBS scene auto-switch | ⭕ Nice to have |
| The Flip working | ⭕ Nice to have |
| madmomTD (vs fallback) | ⭕ Nice to have |

**If all Required items pass: system is GO for live streaming.**
