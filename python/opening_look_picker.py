"""Opening-look picker — choose which visual look the suite boots to.

Writes the chosen look to ``configs/visual_mode.json`` ``"mode"`` BEFORE the
movement tracker / TouchDesigner read it on init, so the suite opens on the
selected look instead of Thomas hand-editing the JSON.

Design:
- **Non-blocking by default.** If stdin is not an interactive TTY (unattended /
  agent-respawn / piped launch) the prompt is skipped and the current
  last-used ``mode`` is kept — an unattended launch always works.
- **Enter = keep last-used.** A bare Enter (or any invalid entry) keeps the
  current mode, so a mis-key never changes the look and never blocks.
- **Never raises.** Any error keeps the existing config and returns None — a
  picker hiccup must never stop the show (matches the suite's fail-safe rule).

Standalone use (any boot path): ``venv/bin/python python/opening_look_picker.py``
Wired into ``system_launcher.py`` (``select_opening_look`` -> here) before the
tracker starts.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

DEFAULT_CONFIG = "configs/visual_mode.json"
# Fallback name/index order if the JSON is unreadable (matches MODE_INDEX in
# movement_tracker.py). The Switch TOP input order must match these indices.
FALLBACK_MODES = {"flame": 0, "lightning": 1, "ascii_lightning": 2}


def choose_mode(
    current_mode: str, modes: dict, interactive: bool, in_stream=None, out_stream=None
) -> str:
    """Return the mode to boot to.

    Args:
        current_mode: the current/last-used mode (the default on empty input).
        modes: ordered name->index map (menu order follows insertion order).
        interactive: True only when we should actually prompt (a TTY).
        in_stream / out_stream: injectable for tests (default stdin/stdout).

    Returns:
        A mode name present in ``modes``. On non-interactive, empty, or invalid
        input, returns ``current_mode`` (or the first mode if current is unknown).
    """
    names = list(modes.keys())
    if current_mode not in names:
        current_mode = names[0] if names else current_mode
    if not interactive:
        return current_mode

    out = out_stream or sys.stdout
    inp = in_stream or sys.stdin
    out.write("\nOpening look — which visual should the suite boot to?\n")
    for i, name in enumerate(names, start=1):
        marker = "  (last used)" if name == current_mode else ""
        out.write(f"  {i}) {name}{marker}\n")
    out.write(
        f"Enter 1-{len(names)} (or a name), or press Enter to keep '{current_mode}': "
    )
    out.flush()

    try:
        raw = inp.readline()
    except (EOFError, OSError):
        return current_mode
    choice = (raw or "").strip().lower()
    if choice == "":
        return current_mode
    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(names):
            return names[idx - 1]
        return current_mode
    if choice in names:
        return choice
    return current_mode  # invalid -> safe default, no re-prompt (non-blocking)


def _resolve_config_path(project_root=None, config_path=None) -> Path:
    if config_path is not None:
        return Path(config_path)
    root = (
        Path(project_root) if project_root else Path(__file__).resolve().parent.parent
    )
    return root / DEFAULT_CONFIG


def pick_and_write(
    project_root=None, config_path=None, in_stream=None, out_stream=None
) -> str | None:
    """Prompt (if interactive), write the chosen mode to the JSON, return it.

    Preserves the rest of the JSON (modes/osc/comment). Never raises: on any
    failure it prints a warning and returns None, leaving the config untouched.
    """
    out = out_stream or sys.stdout
    try:
        path = _resolve_config_path(project_root, config_path)
        with open(path, "r") as f:
            cfg = json.load(f)
        modes = cfg.get("modes") or dict(FALLBACK_MODES)
        current = str(cfg.get("mode", next(iter(modes)))).strip().lower()

        interactive = (
            bool(getattr(sys.stdin, "isatty", lambda: False)())
            if in_stream is None
            else True
        )
        chosen = choose_mode(current, modes, interactive, in_stream, out_stream)

        if chosen != current:
            cfg["mode"] = chosen
            tmp = path.with_suffix(path.suffix + ".tmp")
            with open(tmp, "w") as f:
                json.dump(cfg, f, indent=4)
                f.write("\n")
            tmp.replace(path)  # atomic swap so the tracker never reads a half-file
            out.write(f"Opening look set to '{chosen}'.\n")
        else:
            out.write(f"Opening look kept as '{chosen}'.\n")
        out.flush()
        return chosen
    except Exception as e:  # never let the picker stop the launch
        out.write(f"Opening-look picker skipped ({e}); keeping existing mode.\n")
        out.flush()
        return None


if __name__ == "__main__":
    pick_and_write()
