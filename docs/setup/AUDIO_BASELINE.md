# Audio Reactivity — Baseline Reference (investigate-only, NO code changed)

*2026-09-13. Standing reference for the audio path. **No audio code was changed to
produce this** — the audio device-selection code is exactly as it was (== commit
`bb3c505`); an earlier accidental change was reverted in `f93123c`. Use this doc to
decide the correct device deliberately before touching audio.*

**Live symptom being explained:** music playing, graphics dead, Textport shows
`bass=0.0 mid=0.0 high=0.0` and `audio_spectrum max bin: 0.0` — i.e. `audio_in` is
pointed at a device carrying **no signal**.

---

## 1. The intended audio chain (operator by operator)

```
[physical device] -> audio_in (Audio Device In CHOP)
                     -> audio_spectrum (Audio Spectrum CHOP, FFT)
                        -> aura_compositor.py onFrameStart:
                             _band_energy() over FFT bins -> bass/mid/high (+onset)
                             -> smoothing + multipliers
                             -> glsl.par.value0x..value8x  (uniname0..8)
                                fanned to fire_aura_glsl / lightning_glsl / ascii_lightning_glsl
```

Concrete parameters (all in `touchdesigner/scripts/aura_compositor.py`, as-is):
- **Bands** (`:86-88`): `BASS_BINS=(20,200)`, `MID_BINS=(200,2000)`, `HIGH_BINS=(2000,20000)` Hz.
- **Smoothing** (`:91-93`): bass 0.85 / mid 0.80 / high 0.75 exp coefs.
- **Onset** (`:96-98`): threshold `0.00005`, cooldown 120 ms, decay 0.92.
- **Multipliers** (`:104-108`): `FLAME_INTENSITY_MULT=200`, `TURBULENCE=150`, `DISTORTION=150`, `SPARKLE=8`, `BLOOM=25`. These are large on purpose — see the noise-floor note in §5.
- **Per-frame write** (`:~653`): `value0x..value8x` fanned to all three look TOPs (guarded).

`audio_in -> audio_spectrum` wiring is built in `build_network_v2.py` (`audio_in` →
`audio_spectrum.setInputs([audio_in])`, ~`:330-336`). **Not changed.**

## 2. Where the device is selected today (THREE places — and they disagree)

All three run at load and set `op('/project1/audio_in').par.device`. This is the crux
of the problem: they pick **different** devices, and the last one to run wins.

| # | File:line | Preference order (as-is) |
|---|---|---|
| 1 | `aura_compositor.py:54` `[AUDIO-FIX]` block | **1824c** → BlackHole |
| 2 | `aura_compositor.py:437` `_bootstrap_audio_chain_once()` `chosen` | **1824c** → DDJ → BlackHole → mic |
| 3 | `td_startup_hooks.py:224` `_audio_in_reactive_source()` | **Serato Virtual Audio** → serato → BlackHole, **then RE-ASSERTS after 120 frames (~4 s) to "win the race"** (`:230`) |

**Net effect:** `td_startup_hooks` runs on every project load and its 120-frame
re-assert **overrides** the two aura_compositor picks — so the winner is **Serato
Virtual Audio (`VirtualAudio_UID`)**. On Thomas's live rig that device is **silent**
(nothing is routed into it), which is exactly why `bass=mid=high=0`.

This also matches the live log ordering he saw:
`[AUDIO-FIX] device set to BlackHole2ch_UID` (selector 1: 1824c absent → fell back to
BlackHole) → then `VirtualAudio_UID <== CHOSEN` / `device SET -> VirtualAudio_UID`
(selector 3 / the bootstrap era winning with Serato Virtual Audio).

## 3. What the device was WHEN IT LAST WORKED (from git history + docs)

The record is consistent: the **PreSonus Studio 1824c** is the proven reactive path.

- **`ba3971e` (2026-06-05)** `fix(audio): default audio_in to Studio 1824c, fallback to BlackHole`
  and **`bb65cdc` (2026-06-06)** `fix(audio): reorder bootstrap device preference to 1824c first` —
  the commits that made it react. `logs/iteration_log.md:152`: *"Watch the textport for
  `[AUDIO-FIX] device set to ... 1824c` on load — this is the fix for the `bass=0.0001`
  reading (BlackHole has no Serato signal; 1824c inputs 1-2 do)."*
- **`docs/audits/baseline_outline_audit_2026-06-05.md:45`**: *"Chain confirmed Apr 19:
  PreSonus Studio 1824c → audio_in → audio_spectrum (FFT) → … bass/mid/high/onset →
  flame/turbulence/sparkle/bloom."*
- **`docs/setup/desk_session_v2.md:89`**: *"Play music through the PreSonus 1824c chain
  (Serato master → inputs 1–2)."* Same in `desk_handoff_phase1.md:116`,
  `layer_c_gaussian_splat_scope.md:268/311` ("same device as main suite").

**Then it changed:** the `# 2026-08-01 (Cowork)` era switched selector 3
(`td_startup_hooks`) to prefer **Serato Virtual Audio** first, on the theory that
reading the 1824c "stalled the render on music-start" and that Serato Virtual Audio
"carries the master." That switch — with the 120-frame re-assert — is what currently
wins and is silent. **The most likely last-working device is the 1824c** (Serato
master patched into inputs 1–2); the Aug-1 switch to Serato Virtual Audio is the
prime suspect for the regression.

## 4. Confirmed vs Unknown

**Confirmed (documented / in code):**
- The chain shape (device → audio_in → audio_spectrum → aura_compositor bands → uniforms).
- The band/smoothing/multiplier constants (§1).
- Three competing device selectors exist; `td_startup_hooks`'s re-assert makes **Serato
  Virtual Audio** the final winner right now (§2).
- History says **1824c (Serato → inputs 1–2)** was the working reactive device (§3).

**Unknown — confirm before changing anything:**
1. **Which physical device actually carries Thomas's set right now.** History says 1824c
   inputs 1–2; needs eyes-on confirmation of the current patch/routing.
2. **Is the 1824c even in TD's device menu on the live machine?** Selector 1 fell back to
   BlackHole in the live log, which implies `1824` was NOT enumerated (interface off/renamed,
   or a different UID). Confirm `audio_in`'s Device dropdown list.
3. **Does "Serato Virtual Audio" carry signal in the current Serato config?** It only does
   if Serato's *"Make Audio Available to Other Applications"* is ON and routing the master.
   Right now it is silent → either that toggle is off or it isn't the master.
4. **Is the Aug-1 "1824c stalls the render on music-start" freeze still real?** The comments
   say `outline_glow` blur was later clamped, which was the freeze's cause — so 1824c may now
   be safe again. Unconfirmed.
5. **On-disk code vs the running `.toe`.** `td_startup_hooks.py`'s own header warns that fixes
   "written to disk, never loaded by the running project" is a recurring failure here. The
   live `<== CHOSEN VirtualAudio` came from a `[bootstrap]` selector that on-disk (`bb3c505`)
   prefers **1824c**, not Serato — so the **running** compositor/hooks DAT text inside the
   `.toe` may be an older serato-first version, not the current file. Confirm what's actually
   running (read the live DAT text) before trusting any on-disk edit.
6. **bass ≈ 0.0001 history.** The memory/logs recorded `bass=0.0001` even in "working"
   states, and the multipliers are calibrated against a *"DDJ-SX2 noise floor
   noise_bass≈0.00081"* (`aura_compositor.py:100-103`). So the true signal is tiny and the
   200× multiplier lifts it — meaning a *silent* device reads exactly `0.0` (today), while the
   *right* device reads ~1e-4…1e-2. Distinguish "wrong device (0.0)" from "right device but
   low gain."

## 5. Candidate correct settings (ranked — NOT applied)

Deliberately not changed. When Thomas decides:
1. **Point `audio_in` at the 1824c** (Serato master → inputs 1–2), the documented working
   path — *if* it's enumerated and the freeze is gone. Highest confidence.
2. **Or confirm/enable Serato Virtual Audio** (Serato Prefs → Audio → "Make Audio Available
   to Other Applications") so the Aug-1 selection actually carries signal.
3. Whichever is chosen: make it the single source of truth and stop the three selectors from
   fighting (esp. the `td_startup_hooks` 120-frame re-assert), so a confirmed device can't be
   overridden on the next load. (Design change for later, with Thomas's sign-off.)

**The immediate, no-code check at the desk:** click `/project1/audio_in`, open its **Device**
dropdown, and manually select the device that carries the music; watch `bass/mid/high` go
non-zero. That confirms #1/#2 empirically without any code change. (Note the re-assert in §2
may re-override it ~4 s after a project *load*; a mid-session manual change made after load
should hold.)

---

## Appendix — the two non-audio items (for completeness)

- **Body-mask flip (kept, audio-independent):** `segmentation_mask_reader.py:187`
  `gray = np.flipud(gray)` — corrects the upside-down mask (numpy row 0 = top vs TD
  texture origin bottom-left). Committed in `5a8520b`, retained through the revert.
- **Switch confirmed:** `build_network_v2.py:375`
  `visual_switch.setInputs([fire_glsl, light_glsl, ascii_glsl])` → 3 inputs
  (0=flame, 1=lightning, 2=ascii_lightning). Correct.
