# Engineering Log — TouchDesigner DJ Suite

Newest first. One entry per change set: what, why, evidence, deviations, state.

---

## 2026-09-27 — §8 reactivity slice: fx_react bus + GLITCH (branch `feat/reactivity-foundation-s8`)

**Terminal state: `blocked` on the rig.** Code is built and tested offline. TouchDesigner was not running,
so the command bridge could not be reached (request id 27 at 12:11 got no answer). The slice is staged, not applied.
Thomas applies it with `docs/reactivity_s8_rig_runbook.md`.

**Built (spec §8):**
- **Foundation, `fx_react` bus.** One Script CHOP publishes `kick snare kick_gate snare_gate bass mid high
  energy_slow energy_fast drama`. It is additive: it reads the existing analysis nodes and rewires none of them.
- **`energy_fast`**: a ~1 s Filter CHOP (`fx_energy_fast`) beside the 30 s `fx_energy`. The bus normalizes it
  against a decaying peak, because the raw 1824c energy (~1e-4..0.3) would never cross an absolute threshold.
  `drama` = normalized energy_fast > 0.55.
- **`kick_gate` / `snare_gate`**: Trigger CHOPs **cloned from the live envs** (same threshold/detector),
  with only attack 0.001 s and release 0.03 s replaced.
- **Flame floor**: `REACT_FLOOR` stays 0.30 as the default. A new per-profile `Profile.react_floor` is stored
  on /project1 and read each frame by `aura_compositor._react_floor()`. GLITCH = 0.05. Its startup value is
  None, so a saved .toe always boots on the default floor.
- **Real-FFT bandpass promoted**: `extend_dj_graphics` now emits the same math and bins as the
  `_cowork_freqbands` callback baked into the live .toe.
- **Contract**: `inertia` (low/medium/high, with the high-inertia + gate contradiction rejected), gate/drama/energy_fast
  gains, `needs_react_bus`, and `react_floor`, all enforced by `validate_profile`.
- **GLITCH**: a low-inertia profile bound to the gates and drama. `apply_profile` refuses it when fx_react is
  absent, leaving the current look up.
- **Installer** `install_react_bus.py` builds only the bus nodes and never calls `build_effects()`. It fingerprints
  UV_RAVE-bound parameters before and after. **Self-test** `react_selftest.py` samples the bus for 240 frames and
  prints PASS/FAIL.

**Evidence:**
- `pytest tests/`: 1552 pass, 1 fail. The failure is `test_all_five_toe_files_are_present`, and it is environmental:
  the gitignored launcher copies are generated per checkout. Run against real copies, the toe suite is 45/45.
  Baseline HEAD had 1 failure (a stale launcher manifest), and this branch fixes it.
- UV_RAVE regression receipt: all 8 shipped profiles × {energy, audience} = 32 applied plans were compared
  between HEAD 61ee569 and this branch, with **0 differences**. `_apply_rave_look` is byte-identical.
  The compositor floor resolves to 0.30 with no override.
- The FFT band callback is bit-identical to the live .toe callback across 5 spectrum sizes (test).
- `DJ_Graphics_LIVE.toe` SHA-1 was `cea35657…` before and after. It was never opened for writing. Live-network
  facts were read from a toeexpand of a **scratch copy of the TEMPLATE**, which is byte-identical to live.

**Deviations from the spec (and why):**
- The spec said "drop REACT_FLOOR". Dropping it globally changes UV_RAVE, so the floor is **per-profile**.
- The spec's "150–200 ms release" is stale: the live .toe runs **80/100 ms**. `build_effects()` would reset those
  values to 0.20/0.15, so the rig path is the additive installer, never a rebuild.
- The WIP had `FFT_HIGH_BINS=(13,40)`, but live runs 3–40. It is restored to 3–40, because 13–40 would shift
  UV_RAVE's snare trigger. `mid` is computed inside fx_react, so fx_audio_bands keeps its live 2-channel shape.
- `fx_master_fast` (an identity Math CHOP) was dropped, because the bus normalizes instead.
- Per-profile release knobs (spec §3.4) are **not** built. The gates cover the frenetic need; release knobs are future work.

**Found along the way (not caused by this change):**
- ⚠️ The uncommitted `td_startup_hooks.py` in the main tree (mtime 09-13 21:11, *after* fix 61ee569) re-selects
  **Serato Virtual Audio**, which is silent. The live .toe execs that file from disk at every load. This branch ships the
  61ee569 (1824c) version plus the command-bridge install hunk.
- GLITCH gates are not bound by `STROBE_HZ_CAP`. On fast breaks they can exceed 3 flashes/s (WCAG 2.3.1).
  This is flagged in the runbook.

**Commits:** `750f980` checkpoints the Cowork WIP as found. The next commit is the §8 completion.
