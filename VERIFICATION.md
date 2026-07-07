# VERIFICATION.md — the TD-DJ-Suite read-back protocol

> Added by PLAN-01 (2026-07-06). This is the *closed loop* the project was
> missing for three months: every prior attempt could only **write** into
> TouchDesigner and had no way to **read back** what TD actually did, so every
> session ended at "code done — needs Thomas at the desk," and the desk half ran
> once in ~20 sessions. `verify_network_v2.py` is that read-back channel.

## The one invariant

**The probe is read-only.** It measures; it never sets a parameter. A verify
script that repairs state re-poisons the evidence — exactly what the April
hand-patches did. If a check reports FAIL/WARN, fix it in the builder or by hand
and re-run the probe; never let the probe itself mutate the network.

## What it produces

Two channels, from a single paste:

1. **`logs/verify_report_<YYYYMMDD_HHMMSS>.json`** — the machine-readable
   deliverable. This is the channel a future Claude session reads. The Textport
   is invisible to agents; **the JSON is the contract.**
2. A **PASS/FAIL/WARN table** + `RESULT` line printed to the TD Textport, for
   the human at the desk.

## How to run it (inside TouchDesigner)

Build the network first, then paste into the Textport (Alt+T):

```python
exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/verify_network_v2.py').read())
```

It auto-runs `verify()` on import. Three modes:

| Mode | How | Measures |
|---|---|---|
| **Initial** | plain paste | all checks; `context="initial"` |
| **Post-reload** | `VERIFY_CONTEXT='post_reload'; exec(open('…verify_network_v2.py').read())` after Cmd+S → close → reopen | GLSL binding **persistence** (the April killer); `context="post_reload"` |
| **Live uniforms** | plain paste **twice, ≥5 s apart**, music playing | per-slot `value0x..9x` deltas (two-paste snapshot; no `time.sleep` inside TD) |

The desk runbook (`docs/setup/desk_session_v2.md`, tiers A–D) sequences these.

## The checks and their semantics

| check | PASS means | FAIL means | WARN/INFO means |
|---|---|---|---|
| `ops_exist` | all 16 v2 ops present | ≥1 missing (named) | INFO addendum: stale v1 ghost ops present (never a FAIL) |
| `wiring` | every TOP-chain edge matches the builder | an edge is wrong (actual vs expected printed) | — |
| `glsl_bindings:fire_aura_glsl` / `:lightning_glsl` | `uniname0..9` == canonical map | wrong/empty names; **off-by-one** (uniname0 empty, 1-indexed) called out by name | — |
| `uniforms_alive` | audio slots 0–8 moved between the two pastes | — (never FAILs — movement depends on music/compositor) | WARN: no movement (silence or compositor inactive) |
| `audio_device` | `audio_in` device contains `1824` | — | WARN: BlackHole/other → the `bass=0.0001` silent-audio failure mode |
| `osc` | `oscin1` active on port 7000 | wrong port / inactive | — |
| `syphon` | `syphonOut1` active, sender `TDSyphonSpoutOut` | inactive / wrong sender | INFO: no `sendername` par on this build (candidate name-pars listed) |
| `mask_alive` | `body_mask_top` peak > 0 | op missing | WARN: black mask — tracker off (expected) OR the June-8 Script-TOP failure |
| `fps` | — | — | INFO: `project.cookRate` (editor rate ≠ Perform-Mode rate) |

`RESULT` is `FAIL` if any check is FAIL or ERROR, else `PASS`. WARN and INFO
never flip the result — they surface conditions that depend on external state
(music playing, tracker running, Perform Mode) the probe can't assert alone.

## Failure isolation

Each check runs in its own `try/except`; a raised check is recorded as `ERROR`
and the probe **continues**. Partial reports are deliberate — a single broken
check aborting the run is how the false-"the whole system is broken" spiral
started before.

## JSON schema (agent-facing contract)

```jsonc
{
  "context":  "initial" | "post_reload",
  "timestamp": "YYYYMMDD_HHMMSS",
  "base":      "/project1",
  "checks": [
    { "check": "ops_exist", "status": "PASS|FAIL|WARN|INFO|ERROR|PENDING",
      "detail": "human string", "...": "per-check extras (missing[], deltas[], …)" }
  ],
  "result":  "PASS" | "FAIL",
  "failed":  ["check names with status FAIL"],
  "errored": ["check names that raised"]
}
```

A fresh session given only a JSON path can state which desk items passed by
reading `checks[].status` — no need to ask Thomas anything.

## Known, deliberate deviation: `uTime` (slot 9)

The plan expected slot 9 (`uTime` / `value9x`) to "always move." In the **pure
v2 builder network it does not**: `build_network_v2.py` binds only the uniform
*names* (`uniname0..9`); `aura_compositor.py` writes `value0x..value8x` each
frame and leaves `value9x` alone, because the shaders take time from TD's
built-in `iTime`. `value9x` only moves if a script sets
`value9x.expr = absTime.seconds` (the older `_bind_uniforms_v*.py` did this).

So the probe treats a **static slot 9 as INFO, not FAIL** — reporting it
separately from the audio slots (0–8) so silence is never a false failure. This
is itself a read-back finding: the desk pass will confirm whether Thomas's live
`.toe` has `value9x` bound or relies on `iTime`. Either is valid; the probe just
reports the truth instead of asserting a guess.

## Acceptance mapping (PLAN-01)

1. Build + probe → Textport table + `verify_report_*.json` with `result` set. ✔
2. Cmd+S → reopen → probe → `glsl_bindings` PASS `post_reload`. ← **desk**
3. Tracker running → `mask_alive` PASS. ← **desk**
4. Music playing → phase-2 nonzero deltas on audio slots. ← **desk**
5. `pytest tests/ -v` green incl. fake-op tests; 1-indexed fixture FAILs
   glsl_bindings with an off-by-one message. ✔ (90 passed, 20 skipped)
6. A fresh session, given only the JSON path, can state which items passed. ✔
   (schema above)

Items 2–4 are the desk-verifiable unlocks — the whole point of PLAN-01.
Offline logic (1, 5, 6) is proven by `tests/test_verify_network_v2.py`.
