# CONTINUATION — TouchDesigner DJ Suite

**Driver:** reactivity foundation (spec `docs/ARCHITECTURE_reactivity_foundation.md`).
**Contract:** Done when GLITCH reads as "frenetic" on stage with UV_RAVE unchanged, verified by
`react_selftest.py` PASS + the install's `UV_RAVE fingerprint: UNCHANGED` + Thomas's eyes.
Blocked-on-you: run `docs/reactivity_s8_rig_runbook.md` at the rig; review/merge `feat/reactivity-foundation-s8`.

**State (2026-09-27):** §8 slice built + tested offline on `feat/reactivity-foundation-s8`, NOT applied
(TD was off). Log: `docs/ENGINEERING_LOG.md`.

**Next, in order (spec §8 tail):**
1. Rig-apply + verify §8 (runbook). Decide Cmd+S.
2. Retire the TouchOSC on-device risk (open a `.tosc` on the iPad; regenerate so GLITCH gets a button).
3. `/dj/param/<KNOB>` + `LIQUID` (high inertia) profile.
4. Codify the fixed method as an `add-dj-profile` skill.

**Gotchas:** never run `build_effects()` on the live file (resets hand-tuned 80/100 ms releases);
the main tree's uncommitted `td_startup_hooks.py` is a stale Serato-Virtual-Audio copy.
