"""Tests for opening_look_picker — the startup opening-look selector."""

import io
import json
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

from opening_look_picker import choose_mode, pick_and_write  # noqa: E402

MODES = {"flame": 0, "lightning": 1, "ascii_lightning": 2}


def _choose(current, typed, interactive=True):
    return choose_mode(
        current,
        MODES,
        interactive,
        in_stream=io.StringIO(typed),
        out_stream=io.StringIO(),
    )


def test_numbered_choices():
    assert _choose("flame", "1\n") == "flame"
    assert _choose("flame", "2\n") == "lightning"
    assert _choose("flame", "3\n") == "ascii_lightning"


def test_enter_keeps_last_used():
    assert _choose("lightning", "\n") == "lightning"
    assert _choose("ascii_lightning", "\n") == "ascii_lightning"


def test_name_typed_directly():
    assert _choose("flame", "ascii_lightning\n") == "ascii_lightning"
    assert _choose("flame", "LIGHTNING\n") == "lightning"  # case-insensitive


def test_invalid_input_keeps_default_no_block():
    assert _choose("flame", "9\n") == "flame"  # out of range
    assert _choose("flame", "banana\n") == "flame"  # nonsense


def test_non_interactive_skips_prompt_keeps_default():
    # Unattended launch: never blocks, keeps last-used.
    assert choose_mode("ascii_lightning", MODES, interactive=False) == "ascii_lightning"


def test_unknown_current_falls_back_to_first():
    assert choose_mode("bogus", MODES, interactive=False) == "flame"


def _write_cfg(tmp_path, mode="flame"):
    p = tmp_path / "visual_mode.json"
    p.write_text(
        json.dumps(
            {
                "_comment": "keep me",
                "mode": mode,
                "modes": MODES,
                "osc": {
                    "index_address": "/visual/mode",
                    "name_address": "/visual/mode_name",
                },
            },
            indent=4,
        )
    )
    return p


def test_pick_and_write_sets_mode_and_preserves_json(tmp_path):
    p = _write_cfg(tmp_path, "flame")
    chosen = pick_and_write(
        config_path=str(p), in_stream=io.StringIO("3\n"), out_stream=io.StringIO()
    )
    assert chosen == "ascii_lightning"
    cfg = json.loads(p.read_text())
    assert cfg["mode"] == "ascii_lightning"
    assert cfg["_comment"] == "keep me"  # rest of JSON preserved
    assert cfg["modes"] == MODES
    assert cfg["osc"]["index_address"] == "/visual/mode"


def test_pick_and_write_enter_keeps_mode(tmp_path):
    p = _write_cfg(tmp_path, "lightning")
    chosen = pick_and_write(
        config_path=str(p), in_stream=io.StringIO("\n"), out_stream=io.StringIO()
    )
    assert chosen == "lightning"
    assert json.loads(p.read_text())["mode"] == "lightning"


def test_pick_and_write_missing_file_never_raises(tmp_path):
    out = io.StringIO()
    result = pick_and_write(
        config_path=str(tmp_path / "nope.json"),
        in_stream=io.StringIO("1\n"),
        out_stream=out,
    )
    assert result is None  # no crash, returns None
    assert "skipped" in out.getvalue().lower()
