# Performance Iteration Log

Track systematic changes and their impact on the Generative Stream Graphics system.

## Guidelines

- **ONE variable at a time** - Change only one parameter per iteration
- **Quantify everything** - Record FPS, latency, CPU usage, accuracy
- **Test consistently** - Use same test tracks and movement patterns
- **Document subjectively** - Note feel, vibe, visual impact
- **Keep or revert** - Don't accumulate uncertain changes

---

## Iteration Template

Use VS Code snippet: Type `itlog` in this file to generate new entry

---

## Example Iteration

## Iteration 0 - 2025-12-28

### Hypothesis
Baseline measurement - no changes, establish performance targets

### Changed Variable
**Changed:** None (baseline)
**From:** N/A
**To:** N/A

### Expected Outcome
Establish baseline metrics for all components

### Test Results
- **FPS:** 32 fps (movement tracking)
- **Latency:** 48 ms (audio)
- **Tracking Accuracy:** 94%
- **Subjective Quality:** Smooth tracking, responsive to movement

### Audio Test Tracks
- [x] Amen roller - Good break detection
- [x] Reese bassline - Bass tracking responsive
- [x] Ragga jungle - Vocal samples not interfering
- [ ] Minimal tech-step
- [ ] Double drop

### Movement Test Scenarios
- [x] Standing still - No jitter
- [x] Arm raise on drop - Smooth response
- [x] Dancing to beat - Tracks well
- [ ] Rapid hand movements
- [ ] Big gesture on drop

### Decision
**Status:** Keep

**Reasoning:** Baseline performance meets all targets. Ready for optimization iterations.

### Notes
- Camera positioned 1.5m from DJ booth
- Lighting is key - need consistent overhead light
- MediaPipe model_complexity=1 provides good balance

---

## Iteration 1 - 2026-06-05

### Hypothesis
The overlay reads as an AURA covering the body instead of an OUTLINE because the
Python side emits a *filled, fattened, feathered* silhouette. Extracting a thin
contour at the source (morphological gradient) before any downstream stylization
will produce a body outline, not a blob. (Audit:
`docs/audits/baseline_outline_audit_2026-06-05.md`, Cause A / Section 5 Option 1.)

### Changed Variable
**Changed:** `MovementTracker._process_segmentation` silhouette generation
**From:** `binary = filled mask; cv2.dilate(5x5, iters=2); cv2.GaussianBlur(15x15);
resize(..., INTER_LINEAR)` — a blob grown ~10px and feathered into a ~15px ramp.
**To:** `outline = cv2.morphologyEx(binary, cv2.MORPH_GRADIENT, 3x3);
resize(..., INTER_NEAREST)` — a crisp ~1-2px contour, not re-feathered on resize.

Only one variable changed (the silhouette step). OSC/mmap transport untouched.

### Expected Outcome
`body_mask_top` carries a thin outline instead of a filled body. The live
`contour px=` log should read ~0.3%-2% of frame (a line), not ~25-30% (a blob).
Downstream flame should ride the line; the now-redundant Edge TOP may need
bypassing. No change yet to `fire_aura.glsl` bloom/expansion (desk decision).

### Test Results
- **Offline (synthetic silhouette, no camera/TD):**
  - Old fill path: **94,325 px (30.7% of frame)** — blob.
  - New contour:   **2,640 px (0.86% of frame)** — line. **35.7x thinner.**
  - Connected components: **1** (single closed ring). Contour = 3.3% of fill area.
  - Unit tests: **18 passed** (9 outline + 9 toggle), no regression in existing
    `test_movement_tracker.py` (10 passed, 1 skipped).
- **Live (FPS / latency / accuracy):** PENDING — requires desk pass
  (`docs/setup/desk_handoff_phase1.md`).

### Audio Test Tracks
- [ ] Amen roller — pending desk pass
- [ ] Reese bassline — pending desk pass
- [ ] Ragga jungle — pending desk pass

### Movement Test Scenarios
- [ ] Standing still — pending desk pass
- [ ] Arm raise on drop — pending desk pass
- [ ] Dancing to beat — pending desk pass

### Decision
**Status:** Keep (pending live confirmation at the desk)

**Reasoning:** The math is proven offline — the emitted mask is now a thin,
connected, non-zero contour, dramatically thinner than the blob it replaced. The
remaining widening risks live entirely downstream in TD (redundant Edge TOP,
shader `expansion`, size-12 bloom) and are desk decisions, intentionally left
untouched so the change stays minimal and reviewable.

### Notes
- Also added (same branch, not part of the one-variable outline change):
  net-new `lightning.glsl` (edge-confined electric look) and a flame/lightning
  OSC toggle (`configs/visual_mode.json` -> `/visual/mode`). `fire_aura.glsl` and
  `dj_visuals.toe` were NOT modified.
- Instrumentation added: per-frame `contour px` log (~1x/sec) + `last_contour_px`
  attribute, so the blob-vs-line question is answerable live from the Terminal.
- Optional thicker "neon tube" outline available by uncommenting one dilate line
  in `_process_segmentation`.

---

## 2026-06-07 — Sort-out session (sort what's left, fix it)

Session goal: Thomas at the desk, stuck — render-diag reports `camera_in: MISSING / burst_flash: MISSING / output: MISSING`, audio reads `bass=0.0001`. He's on `feat/td-network-v2-builder` and unsure what's canonical vs WIP.

### What I found

- **`feat/td-network-v2-builder` is a strict superset of `feat/edge-confined-outline-2026-06-05`** (Phase 1). v2-builder branches FROM Phase 1's tip `f779965` and adds: programmatic network builder, GLSL slot growth, GLSL-input-1/2 black wiring, **audio default 1824c→BlackHole fix** (`ba3971e`+`bb65cdc`), 1280x720 mask scaling, 0-indexed `uniname{i}/value{i}x` binding fix (`0a1f2db`). PR #1 is now obsolete; PR #2 is canonical.
- **The "MISSING" alarm was a stale-diagnostic false positive.** `_diag_aura.py` and `_diag_render_chain.py` both checked for **v1 operator names** (`burst_flash`, `noise_embers`, `flame_layers`, `camera_in`, `output`, `motion_energy_top`, `audio_energy_top`, …) that no longer exist in v2. The v2 chain is `body_mask_top → edge_detect → edge_blur → fire_aura_glsl ⇄ lightning_glsl → visual_switch → bloom_blur → bloom_post → final_composite (Null TOP) → syphonOut1`. `camera_in` is **intentionally absent** in v2 — OBS owns the webcam source (see `build_network_v2.py` line ~395 comment).
- **`dj_visuals.toe` is 311010 bytes** — matches the canonical 311KB, not the corrupted 21KB regression.
- **Uncommitted change** to `segmentation_mask_reader.py` was a pure LF→CRLF line-ending rewrite (no content diff with `-w`). Almost certainly TD itself rewrote it on save. Reverted.

### What I fixed

- Reverted line-ending noise on `segmentation_mask_reader.py`.
- Updated `_diag_aura.py` and `_diag_render_chain.py` to the v2 op set so the diagnostic stops crying wolf.

### What's left for desk

- Open `dj_visuals.toe`, verify operators match the v2 chain above. If the .toe predates the v2 builder, run `build_network_v2.py` from a TD textport against a fresh `/project1` to materialize the v2 ops.
- Watch the textport for `[AUDIO-FIX] device set to ... 1824c` on load — this is the fix for the `bass=0.0001` reading (BlackHole has no Serato signal; 1824c inputs 1-2 do).
- Run `_diag_aura.py` again — should now report ALL CLEAN (or only show real errors).
- F1 Perform Mode for framerate.

### Hard rules respected

- `dj_visuals.toe` NOT touched.
- OBS NOT touched ("New Radio DJ Scene" is sacred).
- No merge — verification still owed at the desk.

