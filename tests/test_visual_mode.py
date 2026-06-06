"""
Tests for the flame/lightning visual-mode toggle (Phase 1E).

The tracker reads configs/visual_mode.json and broadcasts the active mode on OSC
(/visual/mode index + /visual/mode_name string) so TouchDesigner can switch the
body-outline shader live. These tests mock all hardware/IO and verify the load,
the OSC emission, and graceful handling of missing/malformed/unknown modes — a
toggle file problem must never take the tracker down.
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))

import movement_tracker as mt  # noqa: E402


def _make_tracker(cfg_path):
    with (
        patch("movement_tracker.mp.solutions.pose.Pose"),
        patch("movement_tracker.udp_client.SimpleUDPClient"),
        patch("movement_tracker.cv2.VideoCapture"),
    ):
        return mt.MovementTracker(
            enable_segmentation=False,
            visual_mode_config_path=str(cfg_path),
        )


def _write(cfg_path, mode):
    cfg_path.write_text(json.dumps({"mode": mode}))


class TestVisualModeToggle:
    def test_default_flame(self, tmp_path):
        cfg = tmp_path / "vm.json"
        _write(cfg, "flame")
        t = _make_tracker(cfg)
        assert t.visual_mode == "flame"
        assert t.visual_mode_index == 0

    def test_lightning(self, tmp_path):
        cfg = tmp_path / "vm.json"
        _write(cfg, "lightning")
        t = _make_tracker(cfg)
        assert t.visual_mode == "lightning"
        assert t.visual_mode_index == 1

    def test_live_switch_reread_on_send(self, tmp_path):
        cfg = tmp_path / "vm.json"
        _write(cfg, "flame")
        t = _make_tracker(cfg)
        # Edit the file after construction; _send_visual_mode re-reads it.
        _write(cfg, "lightning")
        t._send_visual_mode()
        assert t.visual_mode == "lightning"
        assert t.visual_mode_index == 1

    def test_osc_emits_index_and_name(self, tmp_path):
        cfg = tmp_path / "vm.json"
        _write(cfg, "lightning")
        t = _make_tracker(cfg)
        t._send_visual_mode()
        calls = [c.args for c in t.osc_client.send_message.call_args_list]
        assert ("/visual/mode", 1.0) in calls
        assert ("/visual/mode_name", "lightning") in calls

    def test_case_insensitive(self, tmp_path):
        cfg = tmp_path / "vm.json"
        cfg.write_text(json.dumps({"mode": "LIGHTNING"}))
        t = _make_tracker(cfg)
        assert t.visual_mode == "lightning"

    def test_unknown_mode_keeps_previous(self, tmp_path):
        cfg = tmp_path / "vm.json"
        _write(cfg, "lightning")
        t = _make_tracker(cfg)
        _write(cfg, "bogus")
        t._load_visual_mode()
        assert t.visual_mode == "lightning"  # unchanged, no crash

    def test_missing_file_defaults_flame(self, tmp_path):
        t = _make_tracker(tmp_path / "does_not_exist.json")
        assert t.visual_mode == "flame"

    def test_malformed_json_keeps_previous(self, tmp_path):
        cfg = tmp_path / "vm.json"
        _write(cfg, "lightning")
        t = _make_tracker(cfg)
        cfg.write_text("{ not valid json")
        t._load_visual_mode()
        assert t.visual_mode == "lightning"  # unchanged, no crash

    def test_shipped_config_is_valid(self):
        """The committed configs/visual_mode.json must parse and use a known mode."""
        repo = Path(__file__).parent.parent
        cfg = json.loads((repo / "configs" / "visual_mode.json").read_text())
        assert cfg["mode"] in mt.MODE_INDEX
        assert cfg["modes"] == mt.MODE_INDEX
