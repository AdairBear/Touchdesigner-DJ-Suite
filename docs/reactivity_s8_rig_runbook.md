# Rig steps — §8 reactivity slice (fx_react bus + GLITCH)

Branch: `feat/reactivity-foundation-s8` (stacked on `feat/ascii-lightning-layer`).
Do this **before doors**, not mid-set. Step 3 reloads the aura compositor, and
its auto-gain re-learns levels for a few seconds.

Nothing below edits `DJ_Graphics_LIVE.toe` on disk until **you** press Cmd+S in step 8.

## 1. Get the branch onto disk (Terminal)

The main tree holds uncommitted Cowork WIP in the same files. Park it first.
The stash keeps it recoverable.

```bash
cd ~/projects/touchdesigner-dj-suite
git stash push -u -m "pre-s8 cowork WIP (td_startup_hooks copy is STALE: Serato Virtual Audio)" -- \
  touchdesigner/scripts/aura_compositor.py \
  touchdesigner/scripts/dj_graphics_profiles.py \
  touchdesigner/scripts/extend_dj_graphics.py \
  touchdesigner/scripts/td_startup_hooks.py \
  tests/test_dj_graphics_profiles.py \
  tests/test_react_foundation.py \
  docs/ARCHITECTURE_reactivity_foundation.md
git checkout feat/reactivity-foundation-s8
./venv/bin/python -m pytest tests/ -q --no-cov
```

Expected result: all tests pass except two that come from other uncommitted
WIP, not from this branch:
- `test_movement_tracker.py::…::test_init_default_parameters` (uncommitted `movement_tracker.py`).
- `test_dj_profile_toes.py::…::test_all_five_toe_files_are_present`. This one
  clears once you run the optional step below.

Optional: to get a `dj_launcher_GLITCH.toe` pre-show launcher, run the step below.
It reads the live file read-only and aborts if the file's hash changes.

```bash
./venv/bin/python python/dj_profile_toes.py generate
```

## 2. Open the show as usual

Open `~/Desktop/DJ_Graphics_LIVE.toe`. The startup hooks run from disk.

**Check:** the Textport startup report shows `audio_in_src OK device -> …1824c…`.
It must not show Serato Virtual Audio. The uncommitted hooks file selected
Serato Virtual Audio, which is silent. This branch restores the 1824c version
from commit 61ee569. The report also shows `command_bridge OK`.

## 3. Install the bus (Textport, Alt+T)

```python
exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/install_react_bus.py').read())
```

Alternatively, from Terminal via the bridge:
`python3 touchdesigner/scripts/bridge_send.py --timeout 20 --file touchdesigner/scripts/install_react_bus.py`

**Must see all three:**
- `fx_react channels: kick snare kick_gate snare_gate bass mid high energy_slow energy_fast drama`
- `GLITCH registered: True`
- `UV_RAVE fingerprint (N pars): UNCHANGED`

If it prints `CHANGED` or `FAILED`, stop. Close the project **without saving** and send Claude the Textport output.

## 4. Prove the channels fire (play a drum-heavy track through Serato first)

```python
exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/react_selftest.py').read())
```

After about 4 s, the Textport prints `[react_selftest] PASS {...}`. The same
result goes to `.bridge/react_selftest.json`. PASS means all of these hold:
- `kick_gate_hits` ≥ 2
- `kick_gate_width_frames` < `kick_env_width_frames`, so gates are shorter than the envelope
- `energy_fast` spread ≥ 0.1, so energy is no longer DC

A FAIL names its cause. `bass_max=0` means no audio is reaching TD.

## 5. Switch to GLITCH

```python
import dj_graphics_profiles as gp; gp.apply_profile('GLITCH')
```

The report must include `OK   react_floor = 0.05` and end with `0 errors`.
An `ERR fx_react absent` line means step 3 did not run in this session. The current look stays up in that case.

The current `.tosc` has no GLITCH button, because its layout predates the profile. Use the Textport, or regenerate the layout later.

## 6. On stage — what "frenetic" looks like

| Watch for | Means |
|---|---|
| Outline snaps and flashes **on** each kick, gone within 1–2 frames | kick gate works (UV_RAVE glows for ~80 ms instead) |
| A glow pop on each snare that does not smear into the next | snare gate works |
| Between hits the flame drops **near black**, with no steady glow | flame floor is 0.05, not 0.30 |
| Trails clear fast; a break doesn't mush into one blur | short trails re-arm |
| An extra flash on drops and loud passages that stops in breakdowns | drama gate works |

A/B test it with `gp.apply_profile('STROBE_ACID')` (the closest old look), then switch back to GLITCH.

⚠️ **Photosensitivity:** GLITCH flashes on every detected hit. On an amen break that
can exceed 3 flashes/s (the WCAG 2.3.1 general-flash line). `STROBE_HZ_CAP` limits only the
audience strobe, not the gates. If the venue has a flash policy, lower `kick_gate_gain`
in the GLITCH profile or stay on STROBE_ACID.

## 7. Back to UV_RAVE

```python
gp.apply_profile('UV_RAVE')
```

The report shows `OK   react_floor = compositor default`, and the look is the usual one.

## 8. Keep it or throw it away

- **Keep:** Cmd+S. The bus nodes are saved into the live file. The GLITCH floor is
  not saved, because it is stored with a `None` startup value, so every boot starts on the default floor.
- **Discard:** close without saving. Or run this in the Textport:
  `ns={'EXTEND_NO_AUTORUN':True,**globals()}; exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/extend_dj_graphics.py').read(), ns); ns['uninstall_react_bus']()`
  If you have not saved, UV_RAVE was never at risk: the installer never touches its nodes.

## Later: the parked WIP

`git stash list` shows `pre-s8 cowork WIP`. Its `td_startup_hooks.py` is the **stale
Serato Virtual Audio version**. Do not restore that file from the stash.
