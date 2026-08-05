# Graphics Profiles — pre-show look selection

Five swappable looks for the live outline/aura chain, selected before a set (or
between tracks) from the TouchDesigner Textport.

**File:** `touchdesigner/scripts/dj_graphics_profiles.py`
**Tests:** `tests/test_dj_graphics_profiles.py` (98 tests, run on a laptop, no TD needed)

---

## Why profiles rather than more generative layers

The look is already fully parameterised. `extend_dj_graphics.py` builds the
`fx_*` chain (palette / trails / kick / snare / evolution), and
`td_startup_hooks._apply_rave_look()` then tunes it purely by rewriting a Table
DAT and about nine parameter expressions. So an entirely new look costs a table
rewrite plus a handful of `.expr` assignments — instant, reversible, and it
cannot fail to compile.

Adding new generative layers instead would mean new GLSL TOPs, which is the most
expensive failure mode this project has (yellow-triangle compile errors,
resolution mismatches, GPU load). The rig already runs `cookRate 30` to shed
load.

So variation *across* a show is delivered **inside** each profile — via the
existing LFO/energy evolution layer and a per-profile mode schedule — rather
than by adding simultaneous nodes.

---

## The five profiles

| Profile | Use it for | Trails | Kick punch | Mode |
|---|---|---|---|---|
| `UV_RAVE` | Default. The look the rig already boots into. | 0.89 | Big | cycle 30 s |
| `DEEP_LASER` | Deep / rolling sections | 0.94 long | Restrained | lightning (locked) |
| `STROBE_ACID` | Peak time | 0.74 short | Violent | cycle 8 s |
| `VAPOR_UV` | Melodic / softer | 0.92 | Gentle | fire (locked) |
| `MONO_PULSE` | Minimal / clean | 0.85 | Brightness-led | cycle 45 s |

All palettes are neon/UV. The orange hue band (15°–50°) that muddied to brown is
banned at source and enforced by `validate_profile()` — a profile containing it
refuses to apply.

---

## How to preview in TouchDesigner (textport-paste pattern)

1. TD open, tracker running, audio playing.
2. Textport: **Alt+T**.
3. Paste the whole of `touchdesigner/scripts/dj_graphics_profiles.py`, press Enter.
   It **lists the profiles and changes nothing** — pasting is always safe.
4. Then drive it:

```python
list_profiles()               # names + one-line descriptions
show_profile('STROBE_ACID')   # every value it WOULD set — still changes nothing
apply_profile('STROBE_ACID')  # apply it
revert_profile()              # back to UV_RAVE, the shipped look
```

`apply_profile` is idempotent — re-running it is a no-op in effect, so you can
paste and re-apply as often as you like. It never raises: a missing node is
reported in the log, not thrown mid-show.

---

## What to eyeball at the rig

Work down this list with music playing. Each item names what should happen and
what it means if it doesn't.

**1. Paste is inert.**
Paste the file. You should get a profile listing and `nothing applied yet`.
*If the look changes on paste, stop* — that would mean the autorun guard broke.

**2. `apply_profile('UV_RAVE')` is visually a no-op.**
This is the important one. UV_RAVE is built to reproduce the shipped look
exactly, and the test suite pins it against `td_startup_hooks.py`. Applying it
should look **identical** to what the rig already boots into.
*If the look shifts, the two files have drifted* — tell me what changed.

**3. Trails still fade to nothing.**
Watch a held pose for ~5 seconds on each profile, especially `DEEP_LASER` (the
longest trails at 0.94). The trail must decay to black.
*If the frame slowly whites out, the feedback multiply reached 1.0* — quit that
profile and report it. Tests say this cannot happen; the rig is the judge.

**4. Glow punches but never smears.**
On a loud kick the outline glow should visibly bloom, then snap back. The blur
size is hard-clamped at 52 px — the live-proven half of the freeze fix.
*If the glow grows and stays huge, or the frame rate drops, that is the freeze
signature* — `revert_profile()` immediately.

**5. Reactivity is multi-effect, not one blur.** On a kick you should see, at once:
   - outline brightness jump
   - glow bloom
   - a radial zoom punch
   - the kick flash layer add
   - the palette jump to the next anchor (on `UV_RAVE`, `STROBE_ACID`, `MONO_PULSE`)

   On a snare: a shake/displacement plus a brightness pop.
   *If only one of these moves, the envelope CHOPs may not be cooking* — check
   `fx_kick_env` / `fx_snare_env` have live values.

**6. Profiles feel structurally different, not just recoloured.**
`STROBE_ACID` should feel twitchy and short; `DEEP_LASER` slow and smeared.
*If they differ only in colour, the reactivity gains are not landing.*

**7. Watch the frame rate for a full minute with real audio.**
This is the freeze check. Steady 30 fps under music.
*Any stutter that appears only when music plays is the freeze — report it.*

**8. Confirm OBS is untouched.**
The "Radio DJ" scene and Syphon-overlay behaviour must be exactly as before.
Nothing in this file talks to OBS.

---

## Known behaviour: a reload resets your selection

`td_startup_hooks._apply_rave_look()` runs on **every project load** and
rewrites the same palette table and expressions this file sets. So loading the
project returns you to `UV_RAVE`.

That is deliberate and I left it that way: the startup hook owns the go-live
path, and it always brings the rig up in the known-good look. The cost is that
your selection does not survive a reload.

If you want persistence, the exact opt-in patch is documented in the
`PERSISTENCE` block at the bottom of `dj_graphics_profiles.py`. It is a
two-part change to `td_startup_hooks.py` (one tuple entry plus one function).
**I have not installed it** — it changes what happens at showtime, and that is
your call.

---

## Safety invariants (why this cannot reintroduce the freeze)

The freeze had two causes, both guarded here:

1. **The per-bin storm.** A CHOP Execute DAT's `onValueChange` fires once per
   changed *sample*, and `audio_spectrum` has hundreds of bins, so the handler
   ran hundreds of times per frame on the cook thread.

   **This file adds no audio tap and no CHOP Execute DAT.** Every value it reads
   comes from envelope CHOPs that already exist (`fx_kick_env`, `fx_snare_env`,
   `fx_master`) via parameter expressions, which TD evaluates once per cook.
   A test asserts the source stays that way.

2. **The blur explosion.** `outline_glow.size` growing without bound under a raw
   audio value. `glow_size_expr()` has no code path that emits an unclamped
   form; the cap is applied inside the builder, not left to the profile.

Plus one more the tests found worth guarding: a Feedback TOP value-multiply at
≥ 1.0 accumulates forever and whites out the frame, so every trail expression is
clamped below 0.97.

The clamp tests **evaluate** the emitted expressions with the envelopes pinned at
maximum rather than pattern-matching them — a regex can be fooled by a
rearranged expression, an evaluation cannot.

---

## If something looks wrong mid-show

```python
revert_profile()     # back to the shipped UV_RAVE look
```

If that does not clear it, the profile system only writes expressions — reloading
the project re-runs the startup hook and restores the boot look.
