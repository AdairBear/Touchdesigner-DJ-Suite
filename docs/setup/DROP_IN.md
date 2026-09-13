# ASCII + Lightning — Drop-In Guide (3rd look on the /visual/mode chooser)

Turnkey at-desk steps to add **`touchdesigner/shaders/ascii_lightning.glsl`** as a **third
look** on the existing flame↔lightning chooser, toggled live over `/visual/mode` exactly like
the other two. No new asset is required — the glyphs are procedural (baked into the shader).

**Index convention (matches `MODE_INDEX` in `movement_tracker.py` + `modes` in
`configs/visual_mode.json`):**

| `/visual/mode` | mode name | shader | Switch TOP input |
|---|---|---|---|
| 0 | `flame` | fire_aura.glsl | input 0 |
| 1 | `lightning` | lightning.glsl | input 1 |
| **2** | **`ascii_lightning`** | **ascii_lightning.glsl** | **input 2 (new)** |

> This is a **look-toggle inside the reactive-visuals network** (a Switch TOP), NOT a separate
> OBS scene. The OBS-scene-per-layer model is for the bigger layer cuts; switching between
> flame / lightning / ascii-lightning happens on `/visual/mode` with **no OBS scene change**.

> ### 🚫 HARD CONSTRAINTS (live-set safety)
> - **Do NOT touch or reference the "New Radio DJ Scene"** in OBS.
> - **Do NOT enable `touchdesigner/scripts/obs_websocket_td.py`** (dormant OBS audio
>   auto-switcher). Keep it OFF during a live set.

---

## Already applied in this branch (code side)
Both index registries already include the new mode, so `/visual/mode` can carry `2` and the
JSON accepts `"ascii_lightning"`:
- `python/movement_tracker.py` → `MODE_INDEX = {"flame":0, "lightning":1, "ascii_lightning":2}`
- `configs/visual_mode.json` → `modes` gains `"ascii_lightning": 2`

The remaining steps are the at-desk TouchDesigner wiring.

## 1. Create the GLSL TOP

1. Add a **GLSL TOP**, name it `ascii_lightning_glsl`.
2. **Pixel Shader** = a Text DAT pointing at `touchdesigner/shaders/ascii_lightning.glsl`
   (same pattern as `fire_aura_glsl` / `lightning_glsl`). Leave the GLSL **version at TD's
   default** (no `#version` line — TD injects one, as with the other shaders).
3. **Output** RGBA 16-bit float; **Resolution** 1280×720 (16:9). The glyph grid is
   aspect-corrected for 16:9; for another aspect, edit the `cols * 9.0/16.0` term in `main()`.

## 2. Wire the audio uniforms (value1..value9) — same contract as the other looks

Identical uniform names to `fire_aura.glsl` / `lightning.glsl`, so `_bind_uniforms_v4.py`'s
slot layout applies unchanged (slot 0 = `uTime`, slots 1–9 = value1..value9):

| Slot | uniname | value | /audio/* | Reacts as |
|---|---|---|---|---|
| 0 | `uTime` | (expr `absTime.seconds`) | — | clock |
| 1 | `uFlameIntensity` | value1 | bass_rms | glyph brightness + bolt core |
| 2 | `uTurbulence` | value2 | mid | bolt filament chaos |
| 3 | `uDistortion` | value3 | distortion | cell jitter / arc twitch |
| 4 | `uSparkle` | value4 | highs | random bright glyph sparks |
| 5 | `uMotionEnergy` | value5 | motion | scroll speed |
| 6 | `uBassEnergy` | value6 | raw bass | **glyph density (grid pulse)** |
| 7 | `uMidEnergy` | value7 | raw mid | color body |
| 8 | `uHighEnergy` | value8 | raw high | **color shift (blue→cyan/white)** |
| 9 | `uBurstDecay` | value9 | onset_strength | **triggers lightning strikes** |

Easiest: copy the `value0..value9` parameters from `fire_aura_glsl` onto `ascii_lightning_glsl`,
then run the retargeted `_bind_uniforms_v4` snippet in the Textport:

```python
g = op('/project1/ascii_lightning_glsl')   # <- adjust path to where you created it
layout = [
    (0,'uTime','expr','absTime.seconds'),
    (1,'uFlameIntensity','const',0.5), (2,'uTurbulence','const',0.3),
    (3,'uDistortion','const',0.2),     (4,'uSparkle','const',0.0),
    (5,'uMotionEnergy','const',0.0),   (6,'uBassEnergy','const',0.0),
    (7,'uMidEnergy','const',0.0),      (8,'uHighEnergy','const',0.0),
    (9,'uBurstDecay','const',0.0),
]
for i,uname,kind,payload in layout:
    np=getattr(g.par,'uniname'+str(i),None); vp=getattr(g.par,'value'+str(i)+'x',None)
    if np is None or vp is None: print('MISSING slot',i); continue
    np.val=uname
    if kind=='expr': vp.expr=payload; vp.mode=ParMode.EXPRESSION
    else: vp.mode=ParMode.CONSTANT; vp.expr=''; vp.val=float(payload)
g.cook(force=True); print('errors:', g.errors() or 'none')
```

Then have `aura_compositor.py` push value1..value9 into `ascii_lightning_glsl` every frame
(duplicate its existing target / add this TOP to its push list — same as `visual_mode_toggle.md`
step 2 does for `lightning_glsl`). The uniform *names must exist on the TOP* or values never
arrive (the recurring "not reacting" bug).

## 3. Add it as the 3rd input on the /visual/mode Switch TOP

The suite already routes flame/lightning through a **Switch TOP** whose `Index` is driven by
`/visual/mode` (see `docs/setup/visual_mode_toggle.md`). Extend that same Switch:

1. On the existing Switch TOP, **wire a third input** in this exact order (index = mode number):
   - input 0 = `fire_aura_glsl`   (mode 0)
   - input 1 = `lightning_glsl`   (mode 1)
   - input 2 = **`ascii_lightning_glsl`** (mode 2)  ← new
2. Its `Index` stays driven by `/visual/mode` (e.g. `op('oscin1')['visual/mode']`). Sending
   `2` now selects the ASCII look. No other rewiring — the OSC channel already exists.
3. **Routing caveat (full-frame look):** flame/lightning are edge-confined outline overlays
   (premultiplied alpha); **ascii_lightning is a full-frame OPAQUE look**. If the shared
   downstream chain applies the flame **bloom/composite**, mode 2 will look over-bloomed or
   will cover a background layer by design. Two options:
   - Keep it as-is if you want ASCII to fully own the frame when selected (recommended for a
     "cut to the ASCII wall" moment), and keep bloom low for index 2 (same note as lightning).
   - If you instead want it to composite like the outline looks, switch the shader's final line
     to the **premultiplied overlay variant** documented at the bottom of `ascii_lightning.glsl`.

## 4. Set which look loads on open (the default)

The **open-default is the `mode` field in `configs/visual_mode.json`**. `movement_tracker.py`
reads it on init and broadcasts `/visual/mode` on startup, so TD boots to that look:

```json
{ "mode": "ascii_lightning", "modes": { "flame":0, "lightning":1, "ascii_lightning":2 } }
```

Set `"mode"` to `"flame"`, `"lightning"`, or `"ascii_lightning"` — whichever should load on open.
(Belt-and-suspenders: also set the Switch TOP's **Index default parameter** to the same number,
so TD shows the right look even in the split second before the first OSC tick arrives. A Constant
CHOP feeding the Index with that default value works too.)

## 5. Toggle live during the set

Exactly the same controls that already flip flame↔lightning — nothing new to bind:
- **Edit the JSON** `"mode"` and save → switches within ~1 s (tracker re-reads each broadcast).
- **Or** the existing keypress / MIDI pad / UI button that drives `/visual/mode` — just send the
  value **`2`** for ascii-lightning (`0` flame, `1` lightning). A missing/malformed config keeps
  the last good mode, so a toggle hiccup never drops the visuals.

No OBS scene change is needed to switch between these three looks.

## Modes A/B (input 0) — unchanged
- **Mode A — Generative (default):** wire **no inputs**; the shader makes its own ASCII field.
- **Mode B — ASCII-ify a camera/TOP:** wire any TOP into **Input 0** (`sTD2DInputs[0]`); its
  luminance becomes the ASCII source (bolts still strike over it). Auto-detected — black/unwired
  input 0 → stays generative.

---

## Reactive mapping (summary)
- **Bass** (`value1` brightness + `value6` density) → the glyph wall pulses denser/brighter on the low end.
- **Onset** (`value9`) → **lightning strikes** (white glyph flash; bolt column jumps per strike).
- **Mids** (`value2` chaos, `value7` color) → filament turbulence + color body.
- **Highs** (`value4` sparks, `value8` color) → bright glyph sparks + shift toward cyan/white.
- **Distortion** (`value3`) → per-cell jitter (text twitches like arcs). Strike timer ~16 slots/s → punchy at 150–180 BPM.

## Verification status
- **Applied + checked here:** `MODE_INDEX` and `configs/visual_mode.json` now carry
  `ascii_lightning: 2`; the mode name round-trips through the tracker's index resolver
  (`_load_visual_mode` matches against `MODE_INDEX`).
- **Statically verified (shader):** GLSL balance-clean; all 10 uniforms declared with the shared
  names; `out vec4 fragColor` + `TDOutputSwizzle` + `vUV.st`; 8 procedural glyphs.
- **Desk step (Thomas):** widen the Switch TOP + true visual compile happen only with TD open.
  If the TOP errors: check GLSL version is TD's default and that `value1..value9` names exist on
  the Vectors page. If mode 2 looks wrong through bloom, see the §3 routing caveat.
