# ASCII + Lightning — Drop-In Guide (new standalone layer)

Turnkey at-desk steps to add **`touchdesigner/shaders/ascii_lightning.glsl`** as a NEW,
independent audio-reactive layer with its **own Syphon output** and its **own OBS scene**.
No new asset is required — the glyphs are procedural (baked into the shader).

> **This is a standalone look.** It is NOT part of the flame↔lightning `/visual/mode`
> Switch and does NOT need the body-tracking pipeline. Wire it as its own chain.

> ### 🚫 HARD CONSTRAINTS (live-set safety)
> - **Do NOT touch or reference the "New Radio DJ Scene"** in OBS. Add a brand-new scene only.
> - **Do NOT enable `touchdesigner/scripts/obs_websocket_td.py`** (the dormant OBS audio
>   auto-switcher). It must stay OFF during a live set. You cut scenes by hand.

---

## 1. Create the GLSL TOP

1. Add a **GLSL TOP**, name it `ascii_lightning_glsl`.
2. Set **Pixel Shader** to a Text DAT pointing at `touchdesigner/shaders/ascii_lightning.glsl`
   (same pattern as `fire_aura_glsl` / `lightning_glsl`). Leave the GLSL **version at TD's
   default** (do not add a `#version` line — TD injects a modern one, as with the other shaders).
3. **Output**: RGBA, 16-bit float (match the existing shaders).
4. **Resolution**: 1280×720 (16:9). The glyph grid is aspect-corrected for 16:9; if you run a
   different aspect, edit the `cols * 9.0/16.0` term in `main()` to your height/width ratio so
   cells stay square.

## 2. Wire the audio uniforms (value1..value9) — same contract as the other shaders

The shader uses the **identical uniform names** as `fire_aura.glsl` / `lightning.glsl`, so the
existing `_bind_uniforms_v4.py` slot layout applies unchanged — slot 0 = `uTime`, slots 1–9 =
`value1..value9`:

| Slot | uniname | value | Fed from /audio/* | Reacts as |
|---|---|---|---|---|
| 0 | `uTime` | (expr `absTime.seconds`) | — | animation clock |
| 1 | `uFlameIntensity` | value1 | bass_rms | glyph brightness + bolt core |
| 2 | `uTurbulence` | value2 | mid | bolt filament chaos |
| 3 | `uDistortion` | value3 | distortion | cell jitter / arc twitch |
| 4 | `uSparkle` | value4 | highs | random bright glyph sparks |
| 5 | `uMotionEnergy` | value5 | motion | scroll speed |
| 6 | `uBassEnergy` | value6 | raw bass | **glyph density (grid pulse)** |
| 7 | `uMidEnergy` | value7 | raw mid | color body |
| 8 | `uHighEnergy` | value8 | raw high | **color shift (blue→cyan/white)** |
| 9 | `uBurstDecay` | value9 | onset_strength | **triggers lightning strikes** |

**Easiest wiring:** copy the `value0..value9` parameters (Vectors page) from `fire_aura_glsl`
onto `ascii_lightning_glsl`, then run this one-off in the Textport (adapted from
`_bind_uniforms_v4.py`, just retargeted):

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

**Feed the values every frame:** point `aura_compositor.py`'s per-frame uniform push at
`ascii_lightning_glsl` too (duplicate its existing target, or add this TOP to its push list),
exactly as `docs/setup/visual_mode_toggle.md` step 2 does for `lightning_glsl`. The uniform
*names must exist on the TOP* or the values never arrive (the recurring "not reacting" bug).

## 3. Mode A vs Mode B (input 0)

- **Mode A — Generative (default):** wire **no inputs**. The shader generates its own
  lightning/plasma ASCII field. This is the show-ready default.
- **Mode B — ASCII-ify a camera/TOP:** wire any TOP (camera, movie, feedback) into
  **Input 0** (`sTD2DInputs[0]`). Its luminance becomes the ASCII source; bolts still strike
  over it. Auto-detected — if Input 0 is black/unwired the shader stays generative, so leaving
  it connected to a black source is harmless.

## 4. Publish its own Syphon output (macOS)

1. Add a **Syphon Spout Out TOP**, feed it `ascii_lightning_glsl` (via a Null TOP if you like a
   clean tap point).
2. Give the Syphon server a **unique name**, e.g. `ascii_lightning`. Do not reuse the name of
   any existing published look.

## 5. Add it as a NEW OBS scene

1. In OBS, **create a new scene** — e.g. `ASCII Lightning`. **Do not modify "New Radio DJ Scene."**
2. In that new scene add a **Syphon Client** source and select the `ascii_lightning` server.
3. Size/position to the canvas. You now cut to this scene by hand like any other look.
4. **Leave the OBS audio auto-switcher (`obs_websocket_td.py`) disabled** — manual cuts only.

---

## Reactive mapping (summary)

- **Bass** (`value1` brightness + `value6` density) → the wall of glyphs pulses denser/brighter on the low end.
- **Onset** (`value9`) → **lightning strikes**: raises strike probability + fires a white glyph flash; the bolt column jumps per strike.
- **Mids** (`value2` chaos, `value7` color) → filament turbulence + color body.
- **Highs** (`value4` sparks, `value8` color) → random bright glyph sparks + shift toward cyan/white.
- **Distortion** (`value3`) → per-cell jitter so the text twitches like arcs.
- Strike timer runs ~16 slots/s — punchy for a 150–180 BPM breakbeat/jungle set.

## Verification status

- **Statically verified:** GLSL is balance-clean (parens/braces/brackets), all 10 uniforms
  declared with the exact shared names, `out vec4 fragColor` + `TDOutputSwizzle` +
  `vUV.st` per TD GLSL TOP convention, procedural glyph ramp (8 verified 5×5 glyphs).
- **Desk step (Thomas):** true visual compile + look happens only with TD open. If the TOP
  shows a compile error, check the GLSL version is TD's default and that `value1..value9`
  uniform names exist on the Vectors page.

## Transparent-overlay variant (optional)

The shader outputs **opaque** (`vec4(color, 1.0)`) — correct for its own full-frame scene.
To use it as a transparent overlay ON TOP of another layer instead, swap the final line for the
premultiplied version shown in the comment at the bottom of `ascii_lightning.glsl`.
