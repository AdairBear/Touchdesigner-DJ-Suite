# Flame / Lightning Toggle — Wiring Guide

Phase 1E. How to switch the body-outline look between **flame** (`fire_aura.glsl`)
and **lightning** (`lightning.glsl`) live, from a single config file, over OSC.

## How it works

1. `configs/visual_mode.json` holds the active mode:
   ```json
   { "mode": "flame", "modes": { "flame": 0, "lightning": 1 } }
   ```
2. `python/movement_tracker.py` re-reads that file ~1x/sec and broadcasts it on OSC:
   - `/visual/mode`  -> float index: `0.0` = flame, `1.0` = lightning (drives a Switch TOP)
   - `/visual/mode_name` -> string: `"flame"` / `"lightning"` (for DAT-based readers)
3. In TouchDesigner, a **Switch TOP** picks between the two GLSL TOPs using that index.

Editing `mode` in the JSON and saving switches the shader **without restarting the
tracker**. A missing/malformed/unknown config keeps the last good mode — the
outline never goes down because of a toggle hiccup.

## One-time TouchDesigner wiring (at the desk)

> Both shaders share the **same** input/uniform contract (`value1..value9`), so
> you wire the second one exactly like the first — no new uniform plumbing.

1. **Add the lightning GLSL TOP**
   - Create a GLSL TOP named `lightning_glsl`.
   - Point its Pixel Shader DAT at `touchdesigner/shaders/lightning.glsl`
     (same pattern as `fire_aura_glsl`).
   - Give it the same 3 inputs as `fire_aura_glsl`:
     - Input 0: the body contour (the outline mask — `body_mask_top`, optionally
       through the existing `edge_detect` Edge TOP; both work).
     - Input 1: motion energy TOP (optional).
     - Input 2: audio energy TOP (optional).
   - On the Uniform page add `value1`..`value9` (floats), identical to
     `fire_aura_glsl`. Easiest: copy the parameters from `fire_aura_glsl`.

2. **Confirm the uniform push reaches it**
   - `aura_compositor.py` pushes the per-frame audio/motion values into
     `value1..value9`. Point it at (or duplicate its push for) `lightning_glsl`
     so the lightning reacts to audio the same way the flame does.
   - Reminder from the audit: the uniform *names* must actually exist on the TOP
     or the values never arrive (this was the recurring "aura not reacting" bug).

3. **Add the Switch TOP**
   - Create a `Switch TOP`; inputs in this order:
     - input 0 = `fire_aura_glsl`
     - input 1 = `lightning_glsl`
   - Set its `Index` parameter from `/visual/mode`. Wire an OSC In CHOP
     (listening on the tracker's OSC port, channel `visual/mode`) -> the Switch
     TOP `Index`. A CHOP Reference or a tiny parameter expression both work:
     `op('oscin1')['visual/mode']`
   - Route the Switch TOP output into wherever `fire_aura_glsl` currently feeds
     (the `flame_layers` / `bloom` / `final_composite` chain).

4. **Test the switch**
   - Edit `configs/visual_mode.json`: set `"mode": "lightning"`, save.
   - Within ~1 second the Switch TOP index should flip to 1 and the look should
     change to lightning. Set it back to `"flame"` to confirm both directions.

## Notes

- The index is the source of truth for the Switch TOP; `/visual/mode_name` is a
  convenience for DAT/Textport readers and on-screen status.
- Lightning is **edge-confined** by design: it deliberately does *not* use the
  flame's outward expansion or the size-12 bloom. If you route it through the
  flame's bloom chain it will fatten — keep bloom low (or bypass) for lightning,
  per the audit's "edge-confined rendering" principle.
- Adding a third mode later = add it to `MODE_INDEX` in `movement_tracker.py`
  and `modes` in the JSON, add a GLSL TOP, widen the Switch TOP.
