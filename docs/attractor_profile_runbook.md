# Chaotic-Attractor Engine — wiring, runbook, and what is not done yet

> Branch `feat/attractor-profile`. Not merged, not deployed.
> Companion to `docs/dj_graphics_profiles.md` and
> `docs/audience_chat_bridge_runbook.md` — read those first if the profile
> system or the chat bridge is unfamiliar.

Three strange attractors — **Lorenz**, **Thomas** and **Aizawa** — integrated
live and drawn as a glowing point cloud that morphs between forms with the
music. It is a *profile*, not a second visual system: the point cloud renders
**into** the existing `fx_` chain, upstream of the trails, so it inherits the
palette sweep, the feedback trails, the kick flash, the snare shake, the outline
glow, and every audience clamp that already governs those.

---

## 1. What is code-complete vs what needs you at the rig

Honest split. Nothing below was run inside TouchDesigner — there is no TD on
the machine this was written on.

### Code-complete and verified offline (1321 tests pass)

| Piece | Verified how |
|---|---|
| The three ODE systems, RK4, the normalised frame | Integrated for thousands of steps; boundedness, non-collapse and a **positive Lyapunov exponent** measured per system, at both ends of every chaos window |
| The morph (derivative-field blend) | Every blend position integrated and asserted bounded; integer positions asserted identical to the pure system |
| The escape guard | Injected NaN / inf / 1e30 states; reseeding asserted deterministic and on-attractor |
| The trail ring buffer | Fixed size across 500 frames; fades in range; `ordered()` age ordering |
| Every parameter-expression clamp | **Evaluated** (not regex-matched) against a fake `op()` world driven to ±1e9 on every DJ and audience channel |
| The audience caps | Chaos provably in 0..1; morph bias provably under one whole form; speed floor and ceiling |
| Opt-in behaviour | With no `fx_audience`, every emitted expression asserted free of any audience reference |
| The OSC surface | Closed-enum parsing, clamping, release-vs-press, namespace disjointness |
| Cost per cook | Benchmarked: **2.7 ms** absolute worst case, **1.4 ms** for the heaviest shipped profile, against a 33.3 ms budget |

### Needs you, in TouchDesigner, before it is real

1. **Parameter names.** Every write goes through a candidate list
   (`instancesx` / `instancescalex`, `radiusx` / `radius1`, …) because these
   drift between TD builds, but the *right* name in your build is unverified.
   `install_attractor()` logs `none of [...] on <node>` for every miss — read
   that log; it is the punch list.
2. **The instancing wiring.** Direct CHOP instancing (Geometry COMP reading
   `attr_engine` channels) is the design. If your build wants the CHOP→TOP
   route instead (RGB / Fit-to-Square, the way `geo_aura` does it), see §6.
3. **Does it look good.** Camera distance, sprite size, spread and spin are
   judgement calls made without a monitor. Expect to move them.
4. **The GPU shader is unbuilt and uncompiled.** `ATTRACTOR_GLSL_COMPUTE` in
   `attractor_engine.py` is source text only. It is deliberately not wired —
   see §7.
5. **Perform Mode + Cmd+S.** As always: the network only survives a restart if
   you save.

---

## 2. Install, in order

```python
# TD Textport (Alt+T). Assumes extend_dj_graphics.py has already been run.
import sys
sys.path.insert(0, "/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts")

import attractor_pipeline as ap
ap.install_attractor()          # builds the nodes DARK — nothing changes on screen

import dj_graphics_profiles as gp
gp.apply_profile("ATTRACTOR")   # now it lights up
```

`install_attractor()` deliberately does **not** turn the engine on. Building
the nodes and choosing the look are two decisions, the same way installing
`fx_audience` and enabling the audience are.

To remove it completely and restore the original chain wiring:

```python
ap.attractor_teardown()
```

### What gets built

```
attr_dj      Constant CHOP   your live offsets, written by OSC
attr_ctl     Constant CHOP   the resolved knobs — its value pars hold EXPRESSIONS
attr_engine_cb  Text DAT     thin delegate to attractor_engine.cook()
attr_engine  Script CHOP     tx / ty / tz / fade, one sample per point
attr_geo     Geometry COMP   instanced sprites (attr_sprite Circle SOP inside)
attr_mat     Constant MAT    additive, colour tracks the live palette
attr_cam     Camera COMP     tz = 3.5
attr_render  Render TOP      1280x720, bgalpha 0
attr_level   Level TOP       opacity = attr_ctl['enable']   <- the off switch
attr_out     Null TOP
attr_comp    Composite TOP   add(fx_palette_apply, attr_out)
```

### The one structural change

```
before:  fx_palette_apply ─────────────────► fx_trail_comp / fx_trail_feedback
after:   fx_palette_apply ──┐
                            attr_comp (add) ► fx_trail_comp / fx_trail_feedback
         attr_out ──────────┘
```

Two connections move; `attractor_teardown()` puts both back. That position is
the whole integration argument: **upstream of the trails** means the attractor
inherits the trail cap, the flash cap (and with it the photosensitivity
ceiling), the shake, the zoom and the glow. **Downstream of the palette** means
it is coloured by the same sweep the silhouette is.

---

## 3. The looks

| Profile | OSC | Character |
|---|---|---|
| `ATTRACTOR` | `/dj/profile/ATTRACTOR` | Lorenz→Thomas→Aizawa, morphing with the section. 24 trails × 256 |
| `ATTRACTOR_LORENZ` | `/dj/profile/ATTRACTOR_LORENZ` | Locked to the butterfly. Cold, slow, long tails. 16 × 384 |
| `ATTRACTOR_AIZAWA` | `/dj/profile/ATTRACTOR_AIZAWA` | Peak time. Dense, fast, acid/magenta. 48 × 192 |

They appear automatically on the TouchOSC pad (the layout now lays out in two
columns — eight profiles no longer fit one column at a thumb-sized target) and
in `dj_profile_toes.py`'s per-profile `.toe` set. Both were regenerated.

**Tapping any non-attractor profile writes `enable = 0`**, which both hides the
render and short-circuits `cook()` before it integrates. Switching away costs
nothing and leaves nothing running.

---

## 4. Audio reactivity — what moves with what

Everything below arrives through parameter expressions reading CHOPs that
already exist. **No new audio tap. No CHOP Execute DAT.**

| Musical event | Source | Effect |
|---|---|---|
| Section energy | `fx_master['bass']` (the existing 30 s accumulator, ~0.6–1.5) | Opens the **chaos** knob, and leans the **morph** toward the next attractor |
| Kick | `fx_kick_env['bass']` | Chaos punch + **speed** burst |
| Snare / hats | `fx_snare_env['high']` | Shortens the **tail** |
| Kick (via palette) | `fx_palette_engine` | Advances the colour; the particles track it |

### The morph cue, and why it is not an onset detector

`morph_expr` is:

```
base  +  [int(absTime.seconds / cycle)]  +  (energy - 1.0) * gain  +  dj  [+ audience]
```

A section that **builds** pushes the form toward the next attractor; a section
that **empties** lets it settle back. There is no threshold, no state machine
and no drop detector to mistune or desync — the morph is a pure function of a
value the rig already computes. `ATTRACTOR` uses `morph_energy_gain = 0.70`, so
a full build travels about 70% of the way to the next form; `ATTRACTOR_LORENZ`
uses `0.08`, which is a promise that it stays Lorenz.

To cut hard to a form, tap its profile, or ride `/dj/attractor/morph`.

---

## 5. Control surfaces

### Yours (never gated)

```
/dj/profile/<NAME>              the look
/dj/attractor/chaos    -1..1    offset, summed inside the 0..1 clamp
/dj/attractor/morph    -1..1    offset, x3.0 — covers the whole ring
/dj/attractor/speed    -1..1    offset, x2.0
/dj/attractor/trail    -1..1    offset
/dj/attractor/spread   -1..1    offset
/dj/attractor/reset             all offsets back to the profile's own values
```

A tap on any of these arms the same 60 s audience lockout a profile tap does.
From the Textport: `ap.set_dj('chaos', 0.4)` / `ap.zero_dj()`.

### The audience's (gated by all four existing gates)

**Two new nudges, and that is the entire new surface:**

| Chat intent | Target | What it can do |
|---|---|---|
| "more chaos" | `CHAOS` | ±0.20 of the normalised 0..1 chaos knob |
| "change it up" | `MORPH` | ±0.35 of morph position |

Everything else the attractor responds to, the audience already had:
`GLOW`, `FLASH`, `TRAILS`, `SHAKE`, `ZOOM`, `SPEED` all ride the same `fx_`
nodes the attractor renders through, and the **`COLOR_POP` one-shot now snaps
the particle colour too** — through the same 0/1 gate and the same named neon
anchors, so it still cannot land in the banned brown band. No new channel, no
new cap, no second code path.

#### Why these two cannot break anything

- **CHAOS is capped by its own range.** The knob is a normalised 0..1 that
  `attractor_math` maps onto each system's own safe parameter window. There is
  no code path that accepts a raw ρ, b or a. A nudge of 999 is 1.0 is the top
  of a window whose Lyapunov exponent was *measured*. The audience term is
  summed **inside** `min(max(..., 0), 1)`, never beside it.
- **MORPH cannot select a form.** One whole form is 1.0 of morph position and
  `ATTRACTOR_MORPH_SPAN` is 0.35. A fully driven bias slides the blend. Picking
  an attractor is a profile tap or a `/dj/attractor/morph` fader, and both are
  yours.
- **No new flash path.** The engine emits no flashes. Its brightness reaches
  the frame through `fx_kick_bright`, whose expression already bakes in
  `STROBE_HZ_CAP` as a literal. There is nothing here that can flash, so there
  is nothing here that can raise the ceiling.
- **Absence is still the kill switch.** With no `fx_audience` CHOP, every
  expression is emitted in its DJ-only form and there is no term to write into.
  `/dj/panic` zeroes everything and restores `UV_RAVE` exactly as before.

#### One consequence worth knowing at the desk

A `CHAOS` or `MORPH` nudge that arrives while a **silhouette** profile is live
is accepted, written, and does nothing visible — while still spending the
audience's global 10 s NUDGE cooldown. That is a deliberate trade: gating it
would mean the airlock consulting the live look, which is one more thing to be
wrong in the dark.

### After pulling this change — do this once

`AUDIENCE_CHANNELS` gained two entries. `audience_control.set_channel()`
addresses the Constant CHOP **by declared order**, so an `fx_audience` built
before this change has a stale channel map. Re-run:

```python
import audience_control as aud
aud.install_audience_control()
```

The new channels were appended, not interleaved, so nothing else moves — but
the CHOP still needs the two extra slots.

---

## 6. If direct CHOP instancing misbehaves

The fallback is the route `geo_aura` already uses, and the two settings that
silently produce garbage transforms if they are wrong:

```
attr_engine (Script CHOP)
  → CHOP to TOP        Data Format = RGB          (NOT RGBA, NOT float32)
                       Image Layout = Fit to Square
  → Geometry COMP      Instancing on; Instance TX/TY/TZ = the TOP's R/G/B
```

See `touchdesigner/scripts/geometry_instancing_pipeline.py`. This path is worth
the extra hop past roughly 100 k instances — which means the GPU engine, not
this one.

---

## 7. The GPU path — read before you build it

`attractor_engine.ATTRACTOR_GLSL_COMPUTE` is a complete RK4 step of the blended
field, one texel per particle, ready for a ping-pong Feedback TOP over an
RGBA32Float position texture. Its three parameter windows are asserted by the
tests to be **the same numbers** as the Python engine, so the look cannot drift
between paths.

It is shipped as source and **not built**, on purpose: GLSL compile failures are
this project's most expensive class of bug, and a shader that has never been
compiled on your GPU is a claim, not a feature. If you build it:

- Uniform slots are **0-indexed**: `uniname0` / `value0x`. Not `uniformname1`.
  (Slot 0 `uStep`, 1 `uMorph`, 2 `uChaos`.)
- The position texture must be **32-bit float**. 8-bit will quantise the state
  and the trajectory will lock onto a lattice.
- Test it on a spare `.toe` first. Check `glsl.errors()` before wiring output.

---

## 8. Diagnostics

```python
ap.attractor_status()      # which nodes exist, enabled?, last cook's stats
ae.attractor_stats()       # {'escapes', 'escapes_total', 'points', 'substeps', 'cooks'}
```

**Watch `escapes`.** It counts trajectories the guard had to reseed. One or two
on a morph boundary is normal. A count that stays nonzero cook after cook means
a parameter window is wrong, and the engine will say so in the Textport:

```
[attractor] WARN 7 seeds reseeded this cook (chaos=0.94 morph=1.31 speed=2.80).
            A parameter window is probably wrong.
```

That warning is the only signal you get — a silently reseeding engine looks
exactly like a working one right up until the form stops being the form.

### Symptom table

| What you see | Likely cause |
|---|---|
| Nothing renders | `attr_ctl['enable']` is 0 — you installed but did not apply an attractor profile |
| Nothing renders, enable is 1 | `attr_geo` instancing parameter names missed. Re-read the install log for `none of [...]` |
| A single frozen dot | `attr_engine` is not cooking — check the callback DAT imported cleanly |
| Points but no colour | `attr_mat` colour expressions unbound — re-apply the profile |
| A smear, not a form | Two trail systems stacked. Lower `trail_persistence` or the `trail` knob |
| Dotted line, not a curve | Speed too high for the trail length — consecutive points are no longer adjacent |
| Warning spam about reseeds | See above. Do not ignore it |

---

## 9. Files

| File | What it owns |
|---|---|
| `touchdesigner/scripts/attractor_math.py` | The three ODEs, RK4, the normalised frame, the blend, the escape guard, the ring buffer. Zero dependencies |
| `touchdesigner/scripts/attractor_engine.py` | `AttractorSpec`, the caps, the expression builders, `cook()`, the callback source, the GLSL source |
| `touchdesigner/scripts/attractor_pipeline.py` | The TD node builder, the splice, `set_dj()` / `zero_dj()` / `attractor_status()` |
| `touchdesigner/scripts/dj_graphics_profiles.py` | +3 profiles, `Profile.attractor`, `audience_channels_for()`, `attractor_color_expr()` |
| `touchdesigner/scripts/osc_profile_control.py` | `/dj/attractor/*` parsing and routing |
| `touchdesigner/scripts/audience_control.py` | +2 nudge targets |
| `python/chat_bridge/config.py` | +2 nudge targets, so the interpreter's vocabulary includes them |
| `tests/test_attractor_engine.py` | 292 tests: the math, the caps, the audience surface, the contracts |
