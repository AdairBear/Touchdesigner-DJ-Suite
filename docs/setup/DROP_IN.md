# ASCII + Lightning — Drop-In Guide (3rd look, built by the network builder)

The ASCII+lightning look is a **third look** on the `/visual/mode` chooser, wired
**programmatically by `touchdesigner/scripts/build_network_v2.py`** exactly like
flame and lightning — no hand-wiring in the TD GUI.

**Index convention (must match across the stack):**

| `/visual/mode` | mode name | shader | Switch input |
|---|---|---|---|
| 0 | `flame` | fire_aura.glsl | input 0 |
| 1 | `lightning` | lightning.glsl | input 1 |
| **2** | **`ascii_lightning`** | **ascii_lightning.glsl** | **input 2** |

Matches `MODE_INDEX` in `python/movement_tracker.py` and `modes` in
`configs/visual_mode.json` (both already carry `ascii_lightning: 2`).

> Look-toggle inside the reactive-visuals network (a Switch TOP) — **not** a
> separate OBS scene.

> ### 🚫 HARD CONSTRAINTS (live-set safety)
> - **Do NOT touch the "New Radio DJ Scene"** in OBS.
> - **Do NOT enable `obs_websocket_td.py`** (OBS auto-switcher). Keep it OFF.

---

## What Thomas does now: **re-run the build (one Textport paste)**

The network is built programmatically. To make the ASCII node appear and be fully
wired, run the **same build step** already in the desk runbook
(`docs/setup/desk_session_v2.md`) — nothing new:

1. Open `dj_visuals.toe` (the canonical file). Textport: **Alt+T**.
2. Paste and Enter:
   ```python
   exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/build_network_v2.py').read())
   ```
   Expect `[build_v2] === build complete ===`. The builder is **idempotent**
   (`_make()` reuses existing ops), so re-running on an already-built network just
   **adds** `ascii_lightning_glsl` and re-wires the Switch — it won't duplicate or
   disturb flame/lightning.
3. (Optional) Verify:
   ```python
   exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/verify_network_v2.py').read())
   ```

That's it. There is **no** "create a GLSL TOP / widen the Switch by hand" step any
more — the builder does all of it (this replaces the earlier manual instructions).

### What the builder now does automatically (mirrors flame/lightning exactly)
- Creates `ascii_lightning_src` Text DAT loaded from `touchdesigner/shaders/ascii_lightning.glsl`.
- Creates `ascii_lightning_glsl` GLSL TOP via the same `_glsl()` helper: sets the
  shader (`pixeldat`), `1280x720` `rgba16float`, inputs `[edge_blur, zero_src, zero_src]`,
  and names the uniforms `uniname0..9` = `value1..value9` contract (uFlameIntensity …
  uBurstDecay, uTime) — identical to fire/lightning.
- Adds it as **input 2** on `visual_switch` (`setInputs([fire_glsl, light_glsl, ascii_glsl])`),
  so `/visual/mode = 2` selects it.

## Set which look loads on open
Use the launcher picker (`docs/setup/PICKER.md`) — it writes `configs/visual_mode.json`
`"mode"` before the tracker starts, so the suite boots to your chosen look
(`flame` / `lightning` / `ascii_lightning`).

## Toggle live during the set
Same as flame↔lightning: edit `configs/visual_mode.json` `mode` (live ~1 s) or the
existing keypress / MIDI control on `/visual/mode` — send **2** for ascii.
No OBS scene change.

---

## ⚠️ Audio-reactivity note (one honest gap — same for lightning)

The builder **wires** ascii identically to the other looks, but the **per-frame
audio values** (`value0x..value8x`) are pushed by `aura_compositor.py` (the
Execute DAT), and **that script currently writes only `op("fire_aura_glsl")`**
(see its `onFrameStart`, ~line 655). So out of the box, ascii — **like
lightning** — is created, switchable and shader-animated, but its bass/onset/
spectral uniforms won't update until the compositor also targets it.

To make ascii (and lightning) fully audio-reactive, extend the compositor's
writer to loop the three TOPs instead of hardcoding fire — e.g.:

```python
# in aura_compositor.py onFrameStart, replace  glsl = op("fire_aura_glsl")  with:
for _name in ("fire_aura_glsl", "lightning_glsl", "ascii_lightning_glsl"):
    glsl = op(_name)
    if glsl is None:
        continue
    # ... existing glsl.par.value0x..value8x = ... block, unchanged ...
```

`aura_compositor.py` is currently **your uncommitted WIP**, so this change was
**not** made here — apply it in your working copy. (This is a pre-existing
limitation that already affects lightning; it is not introduced by the ascii work.)

## ⚠️ Full-frame vs overlay (a param, not a wiring step)
ascii_lightning is **full-frame opaque** (unlike the edge-confined flame/lightning
overlays). The builder routes the Switch through the flame **bloom** chain, which
will wash an opaque full-frame look. When ASCII is selected, **keep bloom low** (or
bypass it for index 2). If you'd rather ascii composite like the outline looks,
switch its shader's final line to the **premultiplied overlay variant** documented
at the bottom of `ascii_lightning.glsl`. Either way it's a parameter/edit, not a
re-wire.

## Modes A/B (camera input) — unchanged
- **A — Generative (default):** the builder wires input 0 to `edge_blur`; the
  shader auto-detects a black/near-empty input and runs its own ASCII field.
- **B — ASCII-ify a source:** point the GLSL TOP's input 0 at a camera/movie TOP
  instead; its luminance drives the glyphs (bolts still strike over it).
