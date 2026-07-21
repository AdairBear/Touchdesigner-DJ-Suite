# TD Perform Mode — Runbook (cold-executable)

**Goal:** every launch, TD lands fullscreen on the HISENSE showing
`/project1/final_composite` (the OBS feed) with **no editor UI** — so the editor's
~47 ms/frame "Rendering a Window" tax is gone. Verified working cold on
2026-07-18 (TD 099 / build 2022.35320).

## Why F1 failed before, and why this is now reliable

TD's built-in "enter Perform Mode on start" (`project.performOnStart`) is **racy on
this build** — it engaged on some cold launches and not others. F1 also did nothing
because the Perform Window designation (`project.performWindowPath`) had never been
persisted. Both are now fixed, but the **reliable layer is external** and does not
trust TD's internal timing.

## Defense in depth (4 layers, all target `/project1/perform` on the HISENSE)

| Layer | Mechanism | Reliability |
|---|---|---|
| **L1 (primary)** | `perform_enforcer.sh` — external. Waits for TD, forces `ui.performMode=True` via Textport, **verifies** it took, retries until confirmed, **fails LOUD** if not. | ✅ Proven cold (confirmed at attempt 3 while TD was still loading). |
| L2 | `project.performOnStart=True` + `performWindowPath` — TD's native boot-into-perform. | Bonus (racy). |
| L3 | `/project1/perform_autostart` Execute DAT (`onFrameStart` @120f). | Bonus. |
| L4 | **F1** (now that `performWindowPath` persists) / **Esc** to exit. | Manual. |

The launcher fires L1 automatically: `start_tracker.command` (which the launcher runs
first) backgrounds `perform_enforcer.sh`.

---

## Files (authoritative)

- **Launcher opens `~/Desktop/DJ_Graphics.3.toe`** (per `.env` `TD_PROJECT_PATH`).
  This file holds the perform window + settings. It is the one that matters.
  (Older/other `DJ_Graphics.*.toe` on the Desktop are backups/increments — ignore
  them. `*.perfbak.toe` are safety copies.)
- `perform_enforcer.sh` — the reliable trigger.
- `touchdesigner/scripts/_enforce_perform.py` — TD-side helper it drives.
- `check_perform_mode.sh` — fail-loud health check (exit 1 = CRITICAL).
- `touchdesigner/scripts/setup_perform_mode.py` — rebuilds the whole config if ever lost.

---

## COLD RUNBOOK (execute top to bottom)

### A. Normal show start (via the TD DJ Launcher)
1. Hit **ACTIVATE** in the launcher as usual. That's it — `start_tracker.command`
   launches the enforcer, the launcher opens the `.toe`, and within ~15–35 s TD is
   fullscreen on the HISENSE.
2. **Confirm it worked** (do this every show):
   ```bash
   bash ~/projects/touchdesigner-dj-suite/check_perform_mode.sh
   ```
   `PASS` = graphics are in Perform Mode. `CRITICAL` = NOT — see recovery below.
3. Confirm OBS: the **Syphon Client** source shows the composite (it does when
   `syphon_active` is true — the graphics feed is independent of perform mode).

### B. If check says CRITICAL (or you see the editor on the HISENSE)
Force it by hand — either works:
```bash
bash ~/projects/touchdesigner-dj-suite/perform_enforcer.sh   # re-runs the reliable trigger
```
or click the HISENSE / TD and press **F1**. Then re-run the check.

### C. Dev session (you want the editor, NOT fullscreen)
```bash
touch /tmp/td_no_autoperform     # enforcer skips; press Esc if TD still went fullscreen
```
Delete that file (`rm /tmp/td_no_autoperform`) before the show.

### D. Rebuild from scratch (only if the perform window/DAT is ever missing)
In TD Textport (**Dialogs ▸ Textport and DATs**), paste one line:
```
exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/setup_perform_mode.py').read())
```
It rebuilds `/project1/perform`, sets it as the Perform Window, and **saves in place**.
⚠️ TD may increment the filename on save — if so, copy the newest back onto the
launcher target: `cp ~/Desktop/DJ_Graphics.<newest>.toe ~/Desktop/DJ_Graphics.3.toe`.

### E. Final pre-show GPU check (manual)
With music playing, open TD's **Perform Monitor ▸ Analyze** once from the editor
(before going to perform) OR trust that in Perform Mode the editor render cost is
gone — measured `root.cookTime` in perform mode was **0.01 ms** vs the 47 ms editor
"Rendering a Window". Target frame rate is 60; confirm the HISENSE output is smooth.

---

## Monitor mapping (IMPORTANT — HISENSE is the 4K, not the 1080p)
On this rig: **HISENSE = 3840×2160 → TD monitor index 2**; SAMSUNG = 1920×1080 →
index 1; Built-in Retina = main → index 0. Do NOT hardcode a monitor index —
the perform window, enforcer, and DAT all detect **HISENSE by name** (via
`system_profiler`) and resolve the index at open-time, so arrangement drift can't
send graphics to the wrong screen. The enforcer CRITICALs if it can't land on HISENSE.

## Other launcher polish (all wired into start_tracker.command, no rebuild)
- **Serato → SAMSUNG:** `serato_placer.sh` (backgrounded) waits for Serato's window
  and moves it onto the SAMSUNG display (by name). Log: `/tmp/serato_placer.log`.
- **Clean shutdown (no prompts):** run `bash ~/projects/touchdesigner-dj-suite/shutdown_djset.sh`
  to end the set — force-kills Serato (`pkill -9`, no "Are you sure?"), stops the
  tracker/enforcer/placer, quits OBS/BUTT, and closes the tracker Terminal window.
  Serato reopens fine from a SIGKILL. (The launcher's own quit still prompts — use
  this script instead.)
- **Terminal auto-close:** `start_tracker.command` now closes its own Terminal
  window once the tracker exits on shutdown.

## SALVAGE (force perform onto HISENSE without relaunching)
```bash
bash ~/projects/touchdesigner-dj-suite/perform_enforcer.sh
```

## What "active" means (health signal)
The enforcer writes `/tmp/td_perform_state.json`:
`{"active": true, "isOpen": true, "reason": "enforcer", ...}`. `check_perform_mode.sh`
turns that into PASS / CRITICAL and non-zero exit for any monitoring you bolt on.
