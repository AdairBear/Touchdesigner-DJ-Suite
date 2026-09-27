# Architecture & Fixed Method — Reactivity Foundation + Profile System

Status: **DESIGN — for Thomas's approval. Nothing built yet.**
Author: Cowork session, 2026-09-27. Grounded in the repo as it stands, not greenfield.
Scope: the four things asked for — a shared foundation + reactivity engine, a profile contract, TouchOSC live control, and a repeatable "add profile N+1" method.

---

## 0. The one-line summary

You already have most of this. The profile system is a mature data-driven re-parameterizer (`dj_graphics_profiles.apply_profile`), the bridge is solid (`td_command_bridge` + `bridge_send`), live OSC switching works in code (`osc_profile_control`, port 7400 `/dj/*`), and onset detection already exists (`fx_kick_env` / `fx_snare_env` Trigger CHOPs, plus the aura `burst_decay`). The real work is not new machinery — it is **(a) extracting one named reactivity bus so every profile binds to the same channels, (b) fixing the specific tuning constants that flatten the punch, (c) proving the TouchOSC layout on your actual iPad, and (d) writing the method down as a skill so it stops getting re-invented.**

Honest split up front: this is roughly **70% reuse / 30% new**. The new 30% is concentrated in the reactivity bus and the frenetic-fix constants. Everything downstream of that is re-parameterization of nodes you already have.

---

## 1. What already exists (the ground truth)

This is the substrate every design decision below builds on. All paths are real.

### 1.1 The command bridge — REUSE AS-IS
- `touchdesigner/scripts/td_command_bridge.py` — an Execute DAT under `/project1` (`install()`), polling `<repo>/.bridge/request.json` every 15 frames on `onFrameStart`, running code in TD's own context, writing `response.json`. Atomic writes, id handshake, append-only `log.ndjson` audit.
- `touchdesigner/scripts/bridge_send.py` — the agent-side client. `python3 bridge_send.py "<code>"` or `--file`. Exit 0 ok / 2 TD exception / 3 timeout.
- **This is the build channel.** Every step of the fixed method runs through it. No change needed.

### 1.2 The profile system — REUSE, EXTEND
- `touchdesigner/scripts/dj_graphics_profiles.py` (~1777 lines). The core idea (header, lines 3–31): **a profile is DATA, not a node graph.** Applying one rewrites one palette Table DAT and re-binds ~a dozen parameter expressions on nodes that already exist. Nothing is created or deleted. This is deliberate — new GLSL TOPs at showtime are the project's worst failure mode.
- `class Profile` (line 190): identity/palette fields + a "reactivity matrix" of feel-knob gains (`outline_kick_gain`, `glow_kick_gain`, `zoom_kick_gain`, `kick_flash_gain`, `shake_snare_px`, `trail_persistence`, `trail_energy_gain`, `mode`, `mode_dwell_s`, optional `attractor`).
- `PROFILES` registry (line 918) — **8 profiles**: `UV_RAVE` (default/shipped look), `DEEP_LASER`, `STROBE_ACID`, `VAPOR_UV`, `MONO_PULSE`, `ATTRACTOR`, `ATTRACTOR_LORENZ`, `ATTRACTOR_AIZAWA`.
- `validate_profile()` (line 332) is already a **real parameter schema, enforced**: ≥2 palette anchors, RGB in range, no-brown ban, neon floors, `trail_persistence` cap, positive dwells, non-negative gains. A profile that fails refuses to apply.
- Hard safety caps live inside the expression builders (`GLOW_SIZE_HARD_CAP=52`, `TRAIL_VALUEMULT_HARD_CAP=0.97`, `KICK_FLASH_HARD_CAP=14`, `ZOOM_HARD_CAP=1.6`, `STROBE_HZ_CAP=2.0` for WCAG photosensitivity).
- `apply_profile(name)` (line 1462) — live, idempotent, never raises, degrades gracefully if a node is missing.
- `profile_from_toe_name()` (line 1187) + `td_startup_hooks._apply_profile_for_this_toe()` (line 441) — the filename-profile mechanism: `dj_launcher_<NAME>.toe` boots straight into that look. The 8 `.toe` copies in `touchdesigner/profiles/` are byte-identical; only the filename differs.

### 1.3 The audio path — this is where "not frenetic" lives
There are **two parallel audio-reactive subsystems** sharing one front-end (`audio_in` Audio Device In CHOP → `audio_spectrum` Audio Spectrum CHOP):

- **Path A — Aura / body-outline shaders** (`aura_compositor.py`). Python reads the spectrum every frame, computes band energies (`BASS_BINS=(20,200)`, `MID=(200,2000)`, `HIGH=(2000,20000)` Hz), and pushes GLSL uniforms `uFlameIntensity, uTurbulence, uSparkle, uBassEnergy, uMidEnergy, uHighEnergy, uMotionEnergy, uBurstDecay` to `fire_aura_glsl` / `lightning_glsl` / `ascii_lightning_glsl`.
- **Path B — the DJ_Graphics FX CHOP chain** (`extend_dj_graphics.py`), which the **attractor engine** binds to by expression. The three binding fragments (`attractor_engine.py:136–140`):
  ```
  KICK   = op('fx_kick_env')['bass']
  SNARE  = op('fx_snare_env')['high']
  ENERGY = op('fx_master')['bass']
  ```

**Onset/transient detection already exists** in both paths:
- Path B: `fx_kick_env` / `fx_snare_env` are **Trigger CHOPs** — threshold + attack + release. That is discrete per-hit detection, not a continuous envelope. `KICK_THRESH=0.35, ATTACK=0.005s, RELEASE=0.20s`; `SNARE_THRESH=0.30, ATTACK=0.003s, RELEASE=0.15s`.
- Path A: a delta-threshold onset (`bass_delta > ONSET_THRESHOLD=0.00005`, `ONSET_COOLDOWN_MS=120`, decay `0.92/frame`) driving `uBurstDecay`.

So the frenetic problem is **not** "there is no onset detection." It is three specific tuning facts:

1. **The attractor's `ENERGY` term rides `fx_master`, which is a 30-second Filter CHOP** (`EVO_WINDOW_S=30.0`). A 30-second average is effectively DC — it drifts across sections but cannot punch. Only the `*_kick_gain` / `*_snare_gain` terms are fast. → *chaos/morph "energy" reactivity feels sluggish because it is DC by construction.*
2. **Path A is dynamically compressed**: `REACT_FLOOR=0.30` (flame never drops below 0.30), `REACT_CAP=1.0`, and slow-peak auto-gain (`REACT_PEAK_DECAY=0.9985`) that drags loud sustained passages back down. The raw response is already snappy (smooth coefs 0.20–0.25), but the floor/cap/normalization squash the swing. → *it always glows, so hits don't read as hits.*
3. **Trigger release times (150–200ms) blur consecutive hits** at 150–180 BPM (≈330ms kick spacing). Fine for house, too long for an amen break.

**Reusable frenetic parts already in the repo (patches, not yet folded in):**
- `_cowork_freqbands.py` — rewrites `fx_audio_bands` to use **real FFT bins** (`bass = mean(bins 0..2)`, `high = mean(bins 3..40)`) instead of channel-index slicing. Template for a proper multiband split.
- `_cowork_glow_transient.py` — redirects a visual param to the **kick+snare transient envelopes** with a hard clamp: `12 + min(fx_kick_env['bass']*40 + fx_snare_env['high']*15, 40)`. Direct model for transient→param wiring.
- `beat_detector_setup.py` — aspirational madmom/AudioAnalyze onset. **Not installed/wired.** Do not depend on it.

**No true sidechain, drum-bus, or ducking exists.** Bandpass today is crude: FFT bin ranges (Path A) and `fx_kick_sel` / `fx_snare_sel` Select CHOPs isolating `bass`/`high` before the Trigger CHOPs (Path B).

### 1.4 Body motion — additive already, by accident of design
- `python/movement_tracker.py` runs MediaPipe Pose, sends OSC to `127.0.0.1:7000`: `/movement/personN/<metric>` (incl. `motion_energy`), `/movement/avg_energy`, `/visual/mode`.
- In the shaders, motion is **additive/modulation only** — `uMotionEnergy` widens aura expansion and nudges opacity; it never drives the primary look. The attractor engine ignores body motion entirely.
- The body *silhouette contour* (the shape the shaders paint) comes via **shared-memory mmap** (`/tmp/djsam_bodymask_*.raw` → `body_mask_top` → `edge_detect`), not OSC. That is core, but it is an image path, not a reactivity signal.
- **This is exactly the topology you asked for** (audio always-on, body additive) — it just isn't named or documented as a contract. Design below formalizes it.

### 1.5 OSC / TouchOSC — works in code, unproven on device
- **Live control system: UDP port 7400, `/dj/*`** (`osc_profile_control.py`, `audience_control.py`). Received by one **OSC In DAT** `osc_profile_in` → Text DAT handler `osc_profile_handler` (DAT Execute, per-packet — deliberately not a CHOP Execute, for freeze-safety).
  - `/dj/profile/<NAME>` or `/dj/profile "<NAME>"|<int>` → `apply_profile(name)` **live, within a frame, no reload.** Ungated; arms a 60s operator lockout so an audience vote can't flip your tap back.
  - `/dj/attractor/<knob>` where knob ∈ `chaos, morph, speed, trail, spread`, value −1..1 **offset**; `/dj/attractor/reset`. Global, not per-profile.
  - `/dj/audience/*` and `/dj/panic` — fully gated; verbs arrive from the chat bridge, not the pad.
- **`make_touchosc_layout.py` emits real `.tosc` files** to `~/Desktop` (compressed + uncompressed + `.xml` + a fader-free fallback). Modern Hexler next-gen format. Profile button grid + a "LIVE CONTROL" strip (attractor knob faders, crowd gain, KNOBS-0 / CROWD-ON / LOCK-LOOK / PANIC). Addresses are read **live** from the owning modules, so all 8 profiles are served and the layout can never send an address nothing accepts (regression-tested).
- **The separate port 7000 `/td/gen/*` "generative OSC" scheme is markdown-only and unimplemented.** Ignore it; do not build on it.

**Honest gaps:**
- No `.tosc` has ever been opened on your actual iPad. The FADER node type and toggle `buttonType` are *reasoned, not verified* against the app — a prior reasoned-schema attempt shipped an empty layout. **This is the single largest real risk.**
- No per-profile parameter addressing over OSC. Knobs are global offsets; nothing addresses "param X within profile Y."
- Docs say "5 profiles"; code has 8. Prose is stale (generator is correct).

---

## 2. Design part 1 — FOUNDATION: baseline shell + shared reactivity bus

### 2.1 The principle
Keep the "profile = data, not nodes" model. Add **one named reactivity bus** that sits between the audio analysis and every consumer, so a profile binds to *stable channel names* and never re-derives audio itself. Today the attractor hard-codes `op('fx_kick_env')['bass']` in expression strings; Path A computes its own bands in Python. That divergence is why "make it more frenetic" means editing two unrelated places. One bus fixes that.

### 2.2 The bus — `fx_react` (NEW, small)
A single Constant/Script CHOP `fx_react` under `/project1` that publishes the **named control channels** any profile or shader can bind to. It is fed by the existing analysis, not a replacement for it. Proposed channels:

| Channel | Meaning | Source (reuse) | Character |
|---|---|---|---|
| `kick` | bass transient env | `fx_kick_env['bass']` | fast, per-hit |
| `snare` | high transient env | `fx_snare_env['high']` | fast, per-hit |
| `kick_gate` | 1-frame discrete kick pulse | Trigger CHOP, near-zero release | **discrete event** |
| `snare_gate` | 1-frame discrete snare pulse | Trigger CHOP | **discrete event** |
| `bass` / `mid` / `high` | continuous band energy | real FFT bins (`_cowork_freqbands` template) | continuous |
| `energy_fast` | ~1–2s energy | short Filter CHOP (NEW) | medium |
| `energy_slow` | section energy | existing `fx_master` (30s) | DC macro |
| `drama` | threshold-gated "big moment" | `energy_fast > thresh` gate | boolean-ish |

Two energy channels is the key move: keep `energy_slow` for palette drift and morph-on-a-drop (it should be slow), and add `energy_fast` so profiles that want to feel alive have something to bind to that isn't DC. **This is the direct fix for finding 1.3.1.**

### 2.3 The frenetic fixes (these are the "not frenetic enough" answer)
Each is a specific, reversible constant change or a small added node. All flagged reuse/new:

1. **Add `energy_fast`** (~1–2s Filter CHOP) and rebind the attractor's fast-feel terms to it instead of `fx_master`. Keep morph/palette on `energy_slow`. — *NEW node, expression rebind.*
2. **Add `kick_gate` / `snare_gate`** discrete pulses (Trigger CHOP, release ≈ 1 frame) so a profile can fire a *per-hit event* (strobe frame, colour pop, shape jump) that re-arms instantly, distinct from the smoothed envelope. — *NEW, small.*
3. **Shorten the drum release** for the frenetic-class profiles: expose `KICK_RELEASE` / `SNARE_RELEASE` as per-profile feel knobs (default keep 0.20/0.15; frenetic profile drops to ~0.06/0.05). — *reuse Trigger CHOPs, new knob.*
4. **Lower `REACT_FLOOR`** (0.30 → ~0.05) and **loosen the auto-gain** (`REACT_PEAK_DECAY` faster, or a per-profile bypass) so hits punch from near-black instead of from a permanent glow. — *constant change in `aura_compositor.py`, reversible.*
5. **Threshold-gated drama** (`drama` channel): a profile can bind big gestures (whiteout, zoom kick) to `drama` so they only fire above an energy threshold, not continuously. — *NEW gate, reuse of existing clamped expressions.*

### 2.4 Cleaner drum source (the option, honestly scoped)
You asked for a drum-bus / sidechain / bandpass-before-onset option. Ranked by effort/robustness:

- **Now, cheap, robust: real-FFT bandpass before the Trigger CHOP.** Fold `_cowork_freqbands.py` into `extend_dj_graphics` so `fx_kick_env` triggers on `mean(bins 0..2)` (~0–130Hz) and `fx_snare_env` on a tuned high band. This is the single highest-value, lowest-risk audio change. — *reuse existing patch, promote to permanent.*
- **Medium: a dedicated drum-bus input.** Route Serato/your mixer's drum group (or a send) to a separate audio input, analyze *that* for onsets. Cleanest signal, but depends on your hardware routing (PreSonus 1824c is already the confirmed device per `AUDIO_BASELINE.md`). — *NEW; hardware-dependent; needs a bench test.*
- **Later, fragile: sidechain/ducking + ML onset (`madmomTD`).** `beat_detector_setup.py` gestures at this but nothing is wired, and CHOP-Execute-on-audio is the exact pattern the 7400 system avoids for freeze-safety. **Do not put this on the critical path.**

Recommendation: ship the real-FFT bandpass + `energy_fast` + gates + floor fix first. Treat the drum-bus input as a nice-to-have bench experiment, and ML onset as out-of-scope until the rest is proven live.

### 2.5 Baseline shell
The baseline is what `build_network_v2.py` already builds (mask reader → edge → GLSL looks → switch → bloom → Syphon out) plus the `extend_dj_graphics` fx_ chain, brought up by `td_startup_hooks._apply_rave_look()` on every load. **Reuse.** The only foundation addition is `fx_react` + its feeder nodes. `build_network_v2.py` gains one section that creates/reuses `fx_react` idempotently, so a rebuild always restores the bus.

---

## 3. Design part 2 — PROFILE CONTRACT

### 3.1 The contract (mostly already true — formalize it)
A profile is a `Profile` instance in the `PROFILES` registry. It:
1. **Declares data only** — palette, tints, and feel-knob gains. No node creation.
2. **Binds to `fx_react` channel names**, never to raw audio ops. (Change from today, where the attractor hard-codes `fx_kick_env`.) This is the one contract tightening that makes profiles portable across audio changes.
3. **Passes `validate_profile()`** — the existing schema, extended with any new knobs (release times, `energy_fast` gains, gate gains).
4. **Respects hard caps** — expressions clamp inside the builders; a profile cannot exceed `GLOW_SIZE_HARD_CAP`, `STROBE_HZ_CAP`, etc.
5. **Declares an inertia class** (NEW field, see 3.3) so the engine knows how much smoothing to apply and the method knows what's realistic.
6. **Is reachable three ways, all already wired**: `apply_profile(name)` live, `/dj/profile/<NAME>` over OSC, and `dj_launcher_<NAME>.toe` by filename.

### 3.2 The existing aura is already one profile
`UV_RAVE` **is** the shipped aura look, reproduced byte-identically and pinned by the test suite against `td_startup_hooks`. No migration needed — it is the reference profile. New profiles are added beside it.

### 3.3 New profiles you named — with honest inertia matching
Add a `inertia` field to `Profile` (`"low" | "medium" | "high"`) that sets default smoothing and which bus channels dominate. **Match medium inertia to energy — this is a real constraint, not a preference:**

- **Liquid / ripple (`LIQUID`, inertia=high) — "alive while static."** Binds primarily to `bass`, `mid`, `energy_fast` (continuous), a long `trail_persistence`, gentle `glow`/`zoom`. Ripples advance continuously so it breathes even when you're not moving and the track is mid-energy. **It cannot be frenetic and must not try** — a ripple field with 50ms releases looks like noise, not water. Bind it to continuous channels, not gates.
- **Frenetic glitch / trails (`GLITCH`, inertia=low) — strobes with the amen break.** Binds to `kick_gate` / `snare_gate` (discrete), short releases (~0.05s), `drama`-gated strobes and colour pops, low `trail_persistence` so trails clear fast and re-arm. This is the profile the `energy_fast` + gates + floor-fix work exists to enable.
- Existing `STROBE_ACID` is the closest current relative to `GLITCH` (short trails 0.74, violent flash/zoom) but rides the old constants — it is a good A/B reference when tuning `GLITCH`.

### 3.4 Parameter exposure (the last-mile "feel" knobs)
Feel knobs are already centralized as `Profile` constructor kwargs with a docstring schema and `validate_profile` enforcement. Extend, don't restructure:
- Add: `release_kick_s`, `release_snare_s`, `energy_fast_gain`, `kick_gate_gain`, `snare_gate_gain`, `drama_threshold`, `inertia`.
- Keep every knob a plain number/tuple so it stays unit-testable outside TD (the existing discipline — `tests/test_dj_graphics_profiles.py`).

---

## 4. Design part 3 — TOUCHOSC INTEGRATION

### 4.1 Switching — reuse the live path, retire nothing yet
Live profile switching already works: `/dj/profile/<NAME>` → `apply_profile` within a frame. **Keep it.** The filename `.toe` path stays as the pre-show launcher (it reloads TD, so it is unusable mid-set — that's fine, that's its job). Do not try to unify them; they serve different moments.

### 4.2 The address scheme — extend, don't replace
Keep port 7400 `/dj/*`. Additions for per-profile parameter control (the current gap):

```
/dj/profile/<NAME>              press           select profile (EXISTS)
/dj/attractor/<knob>            -1..1 offset    global attractor knob (EXISTS)
/dj/param/<KNOB>                0..1 | -1..1    NEW: live feel-knob on the ACTIVE profile
/dj/visual/<flame|lightning|ascii>  press      NEW: look toggle via source-of-truth (see 4.4)
/dj/audience/*  /dj/panic                        gated crowd layer (EXISTS)
```

`/dj/param/<KNOB>` targets the *currently active* profile — a small handler that writes a live override onto the active profile's applied expressions (glow, trails, flash, zoom, shake, release, drama). This keeps the pad simple (one knob bank that always drives "the look on screen now") and avoids a combinatorial `/dj/param/<PROFILE>/<KNOB>` explosion. If you later want per-profile-remembered knob positions, store them in the `Profile` and let `/dj/param` write back — but start with active-profile override.

### 4.3 Layout authoring — you author, Thomas loads
`make_touchosc_layout.py` already emits the `.tosc`. Extend `build_xml()` to add the `/dj/param/<KNOB>` fader bank (reuse the existing fader emitter that already serves attractor knobs) and the `/dj/visual/*` buttons. Regeneration is byte-stable (uuid5 IDs) and addresses are read live, so the round-trip tests keep guarding it.

### 4.4 The look-toggle subtlety (real gotcha)
`/visual/mode` (flame/lightning/ascii) is rebroadcast ~1×/sec by `movement_tracker.py` from `visual_mode.json`. A TouchOSC button pointing straight at TD's OSC-In would be **overwritten within ~1 second.** Correct wiring: `/dj/visual/<name>` → a small OSC-In handler that **writes `visual_mode.json`** (the single source of truth the tracker then broadcasts). ~1–2h. — *NEW handler.*

### 4.5 The risk you must retire first
**Prove the base `.tosc` on your actual iPad before building anything on top of it.** The FADER node schema and toggle `buttonType` are unverified; a prior reasoned schema shipped an empty layout. The fallback `DJ_Profiles_profiles_only.tosc` (buttons only) exists precisely for this. Method step 5 (verify) makes this a gate, not an afterthought.

---

## 5. Design part 4 — THE FIXED METHOD (add profile N+1, every time the same way)

Codify this as a **skill / SOP** so it is continuous, not re-invented. Each step names its reuse. Terminal states per your standing rules: `success` / `no-op` / `blocked` / `stalled` / `exhausted`.

**Step 1 — SPEC (data only).** Write the new `Profile` literal: palette anchors, tints, feel-knob gains, `inertia` class. Decide which `fx_react` channels it binds to and whether it is low/medium/high inertia. One sentence completion contract: *"Done when the Profile passes `validate_profile` in a unit test."* — *reuse `dj_graphics_profiles`, `tests/`.*

**Step 2 — BUILD ON BASELINE (via the bridge).** No new nodes for a normal profile — it re-parameterizes the foundation. If the profile needs a genuinely new capability (rare), add it to `fx_react` or the baseline, not to the profile. Apply live with `bridge_send.py` calling `apply_profile('<NAME>')`. — *reuse `td_command_bridge` / `bridge_send`.*

**Step 3 — PARAMETERIZE.** Confirm the feel knobs move the look the intended amount; clamp anything that can run away (the hard caps already do this). Tune against the nearest existing relative (`GLITCH` vs `STROBE_ACID`, `LIQUID` vs `VAPOR_UV`). — *reuse the expression builders + caps.*

**Step 4 — REGISTER.** Add to `PROFILES` via `register()`. Generate its `dj_launcher_<NAME>.toe` copy (`dj_profile_toes.py generate`) — the copy is byte-identical, the filename does the work. — *reuse `dj_profile_toes.py`, `profile_from_toe_name`.*

**Step 5 — WIRE INTO TOUCHOSC.** Regenerate the `.tosc` (`make_touchosc_layout.py`) — the profile button appears automatically (addresses read live). Confirm `/dj/profile/<NAME>` switches it live over 7400. — *reuse `make_touchosc_layout`, `osc_profile_control`.*

**Step 6 — VERIFY (the gate — nothing is "done" without a receipt).**
- Unit: `validate_profile` passes; OSC address round-trips (`tests/test_osc_profile_control.py` pattern).
- Live: `bridge_send.py "gp.apply_profile('<NAME>')"` and read back the applied palette/expressions.
- On-device: the button switches the look on the iPad (retire the FADER risk once, permanently).
- Audio: confirm it reacts on a real transient source, not just steady tone.
Terminal state named explicitly. — *reuse `bridge_send`, `tests/`, the diag scripts (`_cowork_diag_reactive*.py`) to read what the running .toe actually contains.*

**Codification:** save this as a repo skill (e.g. `add-dj-profile`) so any future session runs steps 1–6 identically. It complements a `CONTINUATION.md` for the reactivity-foundation work (your standing rule requires one for multi-session projects).

---

## 6. Reuse vs new — the honest ledger

| Component | Verdict | Notes |
|---|---|---|
| Command bridge (`td_command_bridge`, `bridge_send`) | **Reuse as-is** | The build channel. Untouched. |
| Profile data model (`Profile`, `PROFILES`, `validate_profile`, caps) | **Reuse, extend** | Add `inertia` + release/gate/energy_fast knobs. |
| `apply_profile` live re-parameterizer | **Reuse** | Rebind attractor terms to `fx_react` names. |
| Filename-profile (`profile_from_toe_name`, `dj_profile_toes`, `.toe` copies) | **Reuse as-is** | Pre-show launcher. |
| Baseline network (`build_network_v2`, `extend_dj_graphics`, `td_startup_hooks`) | **Reuse, +1 section** | Add `fx_react` bus, idempotent. |
| Onset detection (`fx_kick_env`/`fx_snare_env` Triggers, aura `burst_decay`) | **Reuse** | Already exists. Repurpose, don't rebuild. |
| **`fx_react` reactivity bus** | **NEW (small)** | Named channels incl. `energy_fast`, `kick_gate`, `snare_gate`, `drama`. |
| **Frenetic fixes** (energy_fast rebind, gates, release knobs, REACT_FLOOR/auto-gain) | **NEW (constants + small nodes)** | The direct "not frenetic" answer. All reversible. |
| Real-FFT bandpass before triggers (`_cowork_freqbands`) | **Promote patch → permanent** | Highest-value, lowest-risk audio change. |
| Body-motion additive layer | **Reuse, formalize** | Already additive; write it into the contract. |
| OSC live control (7400 `/dj/*`, `osc_profile_control`) | **Reuse** | Live switching works in code. |
| `/dj/param/<KNOB>` per-profile knob | **NEW (handler + layout)** | Active-profile override; the current gap. |
| `/dj/visual/*` look toggle | **NEW (small handler)** | Must write `visual_mode.json`, not TD directly. |
| TouchOSC layout (`make_touchosc_layout`) | **Reuse, extend** | Add param faders + visual buttons. |
| **On-device `.tosc` verification** | **NEW (test, not code)** | Largest real risk. Retire first. |
| `LIQUID`, `GLITCH` profiles | **NEW (data)** | Built by the fixed method above. |
| Drum-bus input / ML onset | **Out of critical path** | Bench experiment / later. |

## 7. Risks, ranked
1. **TouchOSC on-device.** No `.tosc` ever opened on your iPad; FADER schema reasoned, not verified. → Retire before building the param bank (method step 5, fallback exists).
2. **Audio device contention.** Three selectors fight over the input; `td_startup_hooks` re-asserts Serato Virtual Audio ~120 frames in and currently causes a silent-graphics regression (`AUDIO_BASELINE.md`). Any audio work must settle this first or the reactivity engine has nothing to react to.
3. **Freeze-safety.** The 7400 system uses DAT Execute per-packet, not CHOP Execute, on purpose. New OSC handlers and the `fx_react` feeders must follow that pattern; the unimplemented 7000 `/td/gen/*` CHOP-Execute scheme is the anti-pattern.
4. **Scope creep on audio.** The temptation is ML onset / sidechain. The evidence says the cheap fixes (energy_fast, gates, FFT bandpass, floor) solve "not frenetic" — do those, measure, then decide.

## 8. Recommended first move (for your approval)
Smallest change that proves the whole design: **build `fx_react` with `energy_fast` + `kick_gate`/`snare_gate`, fold in the real-FFT bandpass, drop `REACT_FLOOR`, and cut one frenetic profile (`GLITCH`) that binds to the gates.** That single slice exercises the foundation, the reactivity fix, the profile contract, and the fixed method end-to-end — and you'll see on stage whether "frenetic" is solved before any TouchOSC work. Then retire the iPad risk, then add `/dj/param` + `LIQUID`.

Nothing above is built. Tell me which parts you approve and I'll start with §8.
