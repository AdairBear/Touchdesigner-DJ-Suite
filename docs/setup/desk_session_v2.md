# TD-DJ-Suite — Desk Session Guide (v2 Network, probe-driven)

> Branch: `feat/td-network-v2-builder`
> Last updated: 2026-07-06 (PLAN-01: restructured around the read-back probe)

This guide is now built around `verify_network_v2.py` — a **read-only probe**
that runs *inside* TouchDesigner, measures the actual network state, and writes
a machine-readable report to `logs/verify_report_<timestamp>.json` plus a
PASS/FAIL/WARN table to the Textport. The probe does the measuring that used to
take ~60 min of manual clicking; your remaining job is the ~10 min of aesthetic
judgment a machine can't make.

**Every tier is independently valuable and ≤15 min.** If you stop after any
tier, note the newest `logs/verify_report_*.json` filename and paste it into the
next Claude session — that JSON is all a fresh session needs to know exactly
which of the six desk items passed, without asking you anything.

The probe is **read-only** — it never sets a parameter. It cannot fix anything;
it only tells you (and the next agent) the truth about what TD is doing.

---

## Before you open TouchDesigner

```bash
git checkout feat/td-network-v2-builder && git pull
source venv/bin/activate
pytest tests/test_edge_outline.py tests/test_visual_mode.py tests/test_verify_network_v2.py -v
# Expect: all passed (offline probe logic verified)
```

---

## Tier A — Build + reload persistence (5 min, no camera/music)

*This tier alone settles the two historical killers: 0-indexed GLSL bindings
and bindings evaporating on `.toe` reload (what killed the April go-live).*

1. Open **`dj_visuals.toe`** (repo root — the canonical file).
2. Open the Textport: **Alt+T**.
3. Confirm `REPO_ROOT` at the top of `build_network_v2.py` matches this machine:
   `/Users/thomasadair/projects/touchdesigner-dj-suite`
4. **Build** — paste and press Enter:
   ```python
   exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/build_network_v2.py').read())
   ```
   Expected final lines: `[build_v2] === build complete ===` then a
   `[build_v2] VERIFY (read-back): …` line with the probe one-liner.
5. **Probe** — paste:
   ```python
   exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/verify_network_v2.py').read())
   ```
   Read the table. `ops_exist`, `wiring`, and both `glsl_bindings:*` rows should
   be **PASS**. The probe prints the JSON path — that file is the deliverable.
6. **Reload persistence test** (the April killer, finally measured):
   - **Cmd+S**, then **File → Close**, then reopen `dj_visuals.toe`.
   - Paste, marking the context so the report is labelled `post_reload`:
     ```python
     VERIFY_CONTEXT='post_reload'; exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/verify_network_v2.py').read())
     ```
   - **PASS condition:** both `glsl_bindings:*` rows still **PASS** after the
     reload. If they FAIL now (uniname0 empty / off-by-one), the bindings did
     not persist — that is the exact April failure, now caught by a machine.

➡️ *Stop here? Note the two JSON filenames (initial + post_reload).*

---

## Tier B — Mask is alive (5 min, tracker on)

1. Start the tracker in a Terminal:
   ```bash
   source venv/bin/activate
   python python/movement_tracker.py --max-people 1
   ```
   Watch for: `contour px=NNNN (0.8% of 640x480)` — **0.3%–2% = thin line ✓**,
   **>10% = blob ✗** (something upstream re-filled the mask — stop and flag).
2. Re-run the probe (plain one-liner). `mask_alive` should flip from WARN to
   **PASS** (`body_mask_top` peak > 0) — the June-8 killer (black Script TOP with
   a healthy mmap), finally measured.
3. Eyeball `body_mask_top` in TD: a **silhouette outline**, not a filled body.

➡️ *Stop here? Note the JSON filename.*

---

## Tier C — Live uniforms + look toggle (5 min, music on)

1. Play music through the PreSonus 1824c chain (Serato master → inputs 1–2).
2. **Live-uniform test (two pastes).** Paste the plain probe one-liner **twice,
   ≥5 s apart**:
   - 1st paste: `uniforms_alive` = **PENDING** (snapshot stored).
   - 2nd paste: `uniforms_alive` computes per-slot deltas.
   - **PASS:** nonzero deltas on the audio slots (0–8) → `aura_compositor` is
     writing live uniforms. Silence → WARN (expected, not a failure).
   - Slot map on `fire_aura_glsl`'s **Vectors** page (0-indexed, per-component):
     | par | uniform |
     |-----|---------|
     | `value4x` | `uMotionEnergy` |
     | `value5x` | `uBassEnergy` |
     | `value6x` | `uMidEnergy` |
     | `value7x` | `uHighEnergy` |
     | `value9x` | `uTime` (shader-driven; static value9x is normal) |
   - If audio slots stay at 0 with music playing: `aura_compositor` Execute DAT
     may be inactive → check **Active = On, Frame Start = On**, and that
     `audio_in` device is the 1824c (`audio_device` row on the probe).
3. **Look toggle** — switch flame↔lightning via the config file:
   ```bash
   python -c "import json,pathlib; pathlib.Path('configs/visual_mode.json').write_text(json.dumps({'mode':'lightning'}))"
   # ...and back:
   python -c "import json,pathlib; pathlib.Path('configs/visual_mode.json').write_text(json.dumps({'mode':'flame'}))"
   ```
   `visual_switch` index should change within ~1 s (the running tracker is the
   OSC sender on port 7000). Eyeball: flame rides the contour and licks off it;
   lightning replaces it cleanly.
4. **Bloom / haze too strong?** (aesthetic judgment — probe can't do this):
   drop `bloom_blur` `size` toward 1–2, or reduce `expansion`/`flameExpand` in
   `fire_aura.glsl`. Note the change in `logs/iteration_log.md`.
   *(Once PLAN-02 lands, tune these via `configs/visual_params.json` hot-reload
   instead of editing GUI/GLSL by hand.)*

➡️ *Stop here? Note the phase-2 JSON filename.*

---

## Tier D — Syphon → OBS + Perform Mode FPS (5 min)

1. In OBS, add a **Syphon Client** source pointing at sender name
   **`TDSyphonSpoutOut`** — in a **new dev/scratch scene**.
   **Never touch "New Radio DJ Scene" — it is sacred** (additive only).
2. Confirm the outline overlay appears in the OBS preview.
3. In TD press **F1** (Perform Mode). FPS should jump from ~7 (editor) to 30–60.
   The probe's `fps` row reports `project.cookRate`, but editor cook rate is not
   the delivered rate — read the real number in Perform Mode.
4. Log the observed Perform-Mode FPS in `logs/iteration_log.md`.

➡️ *Done. The newest `logs/verify_report_*.json` records items 1, 4, 5 and most
of 2/6 as machine-checked; your notes cover the aesthetic calls.*

---

## What the probe measures (map to the old 6-item checklist)

| Old desk item | Probe check(s) | Human still judges |
|---|---|---|
| 1. GLSL bindings + **persistence** | `glsl_bindings:*` (init + `post_reload`) | — |
| 2. Audio device / uniforms arrive | `audio_device`, `uniforms_alive` | music actually audible |
| 3. Mask not black | `mask_alive` | outline-not-blob shape |
| 4. Ops present + wired | `ops_exist`, `wiring` | — |
| 5. OSC / Syphon up | `osc`, `syphon` | overlay looks right in OBS |
| 6. FPS | `fps` (editor caveat) | Perform-Mode number, feel |

---

## OBS auto-switcher note (dormant — read before enabling)

`touchdesigner/scripts/obs_websocket_td.py` contains a beat-reactive scene
switcher targeting `'Layer 0 — Drop'` / `'Layer 0 — Build'` / `'Layer 0 — Baseline'`.
It is **not active**. If you enable it, first **create those three scenes in OBS**
(they don't exist yet — that's PLAN-03). The **"New Radio DJ Scene" is sacred and
must never be touched** — the SCENES dict is coded to never reference it. Enable
only after those scenes exist and you've tested in a scratch OBS setup.
