# Opening-Look Picker

Choose which visual look the suite boots to at launch, instead of hand-editing
`configs/visual_mode.json`.

## What it does

When you start the suite via **`python/system_launcher.py`**, right after the
dependency/camera pre-flight and **before** the movement tracker + TouchDesigner
start, it prompts:

```
Opening look — which visual should the suite boot to?
  1) flame  (last used)
  2) lightning
  3) ascii_lightning
Enter 1-3 (or a name), or press Enter to keep 'flame':
```

Your choice is written to `configs/visual_mode.json` `"mode"` **before** the
tracker reads that file on init and broadcasts `/visual/mode` — so the suite
opens on the look you picked. (`0=flame, 1=lightning, 2=ascii_lightning`, matching
`MODE_INDEX` in `movement_tracker.py` and the Switch TOP input order.)

## Behaviour (robust / non-blocking)

- **Enter = keep last-used.** A bare Enter keeps the current `mode`.
- **Invalid entry = keep last-used.** A bad number/name never re-prompts and never
  changes the look.
- **Unattended launch never blocks.** If stdin isn't an interactive terminal
  (agent respawn, piped, headless), the prompt is skipped and the existing mode is
  kept — automated launches still work.
- **Never stops the show.** Any error (unreadable JSON, etc.) is caught; the launch
  continues with the existing mode. The write is atomic (temp file + rename) so the
  tracker never reads a half-written file.

## How to use

- **Normal:** launch the suite as usual — `venv/bin/python python/system_launcher.py`
  — and answer the prompt.
- **Standalone (any boot path, e.g. if you start via `start_tracker.command`):**
  run the picker first, then launch:
  ```bash
  venv/bin/python python/opening_look_picker.py
  ```
  It writes `configs/visual_mode.json` and exits; then start the suite/tracker.

> Note: `start_tracker.command` is intentionally **not** modified — it is
> auto-invoked (agent respawn / concurrent start lock), so a blocking prompt there
> would hang unattended restarts. Use `system_launcher.py` (which calls the picker)
> or run the picker standalone before that path.

## Live switching still works

The picker only sets the **opening** look. Switching looks **during** the set is
unchanged — edit `configs/visual_mode.json` `mode` (live, ~1 s) or use the existing
keypress / MIDI control on `/visual/mode` (send `0`/`1`/`2`). See
`docs/setup/visual_mode_toggle.md` and `docs/setup/DROP_IN.md`.

## Files

- `python/opening_look_picker.py` — the picker (standalone-runnable + importable).
- `python/system_launcher.py` — calls `select_opening_look()` in `run()` before the tracker.
- Tests: `tests/test_opening_look_picker.py` (10 tests: numbered/name/Enter/invalid/
  non-interactive/atomic-write/JSON-preservation/never-raises).
