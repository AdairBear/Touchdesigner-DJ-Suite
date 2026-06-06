# Desk Handoff — Phase 1 Validation

Everything in Phase 1 that can be done without you at the desk is **done and on
the branch** `feat/edge-confined-outline-2026-06-05`. This checklist is the part
that needs **you, at the desk, with TouchDesigner + OBS open**. Work top to
bottom; each step says what to do and what "good" looks like.

Source of truth for the why: `docs/audits/baseline_outline_audit_2026-06-05.md`.

---

## 0. Before you start

- [ ] Pull the branch: `git checkout feat/edge-confined-outline-2026-06-05 && git pull`
- [ ] Activate the venv: `source venv/bin/activate`
- [ ] Confirm tests still pass on your machine:
      `pytest tests/test_edge_outline.py tests/test_visual_mode.py -v`
      Expect **18 passed**.

---

## 1. Confirm the canonical `.toe` (resolves the size-regression flag)

The audit flagged a size regression across the "live" files (311 KB -> 25 KB ->
21 KB) and could not tell which `.toe` is the real current network without TD.

- [ ] Open the **311 KB** `dj_visuals.toe` in TouchDesigner.
- [ ] Verify the full aura chain exists:
      `body_mask_top -> edge_detect -> edge_blur -> fire_aura_glsl ->
      flame_layers -> bloom -> final_composite -> syphonOut1`.
- [ ] If that network is intact -> **this is canonical**. If it's missing
      operators, open the 21-25 KB `dj_visuals.live_*` files and compare.
- [ ] **Decide and write it down** (a one-line note in `logs/iteration_log.md`):
      which `.toe` is the working file going forward. Everything below assumes
      you've picked one.

> Reminder: do not let me (Claude) touch `.toe` files — they're binary and only
> you in TD can change them safely.

---

## 2. See the outline actually change shape (the core Phase 1 payoff)

This is the whole point: the Python side now emits a **thin contour**, not a
filled+blurred blob.

- [ ] Start the tracker from **Terminal** (camera permission is scoped to
      Terminal, per the audit):
      `python python/movement_tracker.py --max-people 1`
- [ ] Watch the Terminal log. ~1x/sec you should see lines like:
      `contour px=NNNN (0.8% of 640x480) — thin outline if low, blob if high`
      - **Good:** roughly **0.3%–2%** of frame. That's a line.
      - **Bad:** double-digit % (e.g. 25–30%). That would mean a blob is still
        being emitted — stop and tell me; something upstream re-filled it.
- [ ] In TD, look at `body_mask_top` (the mask coming over the mmap). It should
      now read as a **silhouette outline**, not a filled body.

### If the old Edge TOP now double-edges the outline

Because the mask is *already* an outline, the downstream `edge_detect` Edge TOP
is now redundant and may thin/dash the line oddly.

- [ ] Try **bypassing `edge_detect`** (feed `body_mask_top` straight to the
      shader / Switch TOP). Compare with it enabled. Keep whichever looks like a
      clean continuous line.
- [ ] If you keep `edge_detect`, set `edge_blur` size to ~1 (the audit's Option 2
      note) so it doesn't re-feather the line.

---

## 3. Confirm the flame still rides the line (not a haze)

- [ ] With `mode: "flame"` (default) in `configs/visual_mode.json`, view the
      `fire_aura_glsl` output.
- [ ] **Good:** flame sits on/near the contour line and licks off it.
- [ ] **If it still reads as a body-covering haze:** the shader's own expansion +
      the size-12 bloom are widening the now-thin line. Per the audit (Cause C):
      - drop `bloom_blur` size from 12 toward ~2–4,
      - in `fire_aura.glsl` reduce the `expansion` terms / `flameExpand`.
      Note what you changed in the iteration log. (I did **not** modify
      `fire_aura.glsl` — that stays as-is until you decide at the desk.)

---

## 4. Wire + test the lightning toggle

Full wiring steps: `docs/setup/visual_mode_toggle.md`. Quick version:

- [ ] Add a GLSL TOP `lightning_glsl` pointing at
      `touchdesigner/shaders/lightning.glsl`; same 3 inputs and same
      `value1..value9` uniform page as `fire_aura_glsl`.
- [ ] Make sure `aura_compositor.py` pushes the uniforms to `lightning_glsl` too
      (so it reacts to audio).
- [ ] Add a `Switch TOP`: input0 = `fire_aura_glsl`, input1 = `lightning_glsl`;
      drive its `Index` from OSC `/visual/mode`.
- [ ] Toggle test: edit `configs/visual_mode.json` `mode` -> `"lightning"`, save.
      Within ~1s the look should swap. Switch back to `"flame"`. Both directions.
- [ ] Lightning should **flicker/strike on onsets** and **hug the contour**
      (sharp blue/white filaments, not a glow). If it blooms into a haze, it's
      going through the flame's bloom chain — keep bloom low for lightning.

---

## 5. Audio reactivity (confirm uniforms actually arrive)

The audit's recurring blocker: the GLSL uniform *names* were sometimes not on the
TOP, so audio values never reached the shader.

- [ ] Play music through the PreSonus 1824c chain.
- [ ] In the GLSL TOP's parameters, watch `value1..value9` — they should move
      with the audio. If they're stuck at 0 while music plays, the uniform names
      on the TOP don't match what `aura_compositor.py` pushes — re-apply the
      uniform wiring (and consider persisting it so it survives `.toe` reloads).
- [ ] Confirm color/intensity shifts with bass/mid/high and that onsets trigger
      bursts (flame flares / lightning strikes).

---

## 6. Output to OBS

- [ ] Confirm `syphonOut1` (`TDSyphonSpoutOut`, active) is publishing.
- [ ] In OBS, the Syphon Client source shows the outline overlay.
- [ ] Check scene composition (overlay over camera/scene as intended).
- [ ] **Use Perform Mode (F1)** for framerate — the audit notes ~7 FPS in editor
      mode vs 30–60 in Perform Mode.

---

## 7. Performance feel (subjective — your call)

- [ ] Does the outline track cleanly during dancing / big gestures?
- [ ] Does it react to the music the way you want (flame movement, color shift,
      lightning strikes on the beat)?
- [ ] Log a real entry in `logs/iteration_log.md` (FPS, latency feel, keep/revert
      decision). Iteration 1 (this Python fix) is already started there.

---

## After the desk pass

Tell me which of these is true so I can take the next step:

- **Outline is thin and correct, flame rides the line, toggle works** ->
  approve/merge the PR, and we move to fast-follow polish (bloom/expansion
  tuning, color-to-music hue cycling, the lightning's audio mapping).
- **Outline is thin but flame still hazes** -> I'll prep the `fire_aura.glsl`
  expansion/bloom reduction (Option 2) as a follow-up commit for you to apply.
- **Contour px is still high (blob)** -> something re-fills upstream; send me the
  `contour px=` log line and I'll trace it.

## Hard rules I followed (so you know the state)

- No pushes to `main`; nothing merged — the PR is **draft, holding for this desk
  verification**.
- `dj_visuals.toe` and `fire_aura.glsl` were **not modified**. Lightning is
  net-new alongside.
- No live system was touched (no TD/OBS/tracker were running at build time).
