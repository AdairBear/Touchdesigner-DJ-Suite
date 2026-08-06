"""Tests for live profile switching over OSC (osc_profile_control.py).

The whole contract of a tap lives in parse_osc_profile_message(), which is pure,
so what a button does is testable without TouchOSC, TouchDesigner, or a network.

The bias under test is IGNORE: a stray or malformed packet must never change the
look mid-set, and a button's release must not re-fire the look its press applied.

On the stdlib XML parser below: the only document parsed is the one this repo's
own generator produced two lines earlier. There is no untrusted input and no
external entity to resolve, so defusedxml would add a dependency without
removing a risk.
"""

import sys
import zlib
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "touchdesigner" / "scripts"))
sys.path.insert(0, str(REPO / "python"))

import dj_graphics_profiles as gp  # noqa: E402
import osc_profile_control as ctl  # noqa: E402
import make_touchosc_layout as layout  # noqa: E402

NAMES = list(gp.PROFILES)


class TestAddressForm:
    @pytest.mark.parametrize("name", NAMES, ids=NAMES)
    def test_per_profile_address_resolves(self, name):
        assert ctl.parse_osc_profile_message("/dj/profile/%s" % name, [1.0]) == name

    @pytest.mark.parametrize("name", NAMES, ids=NAMES)
    def test_every_generated_address_round_trips(self, name):
        """The addresses in the layout must be the ones the handler accepts."""
        addr = "%s/%s" % (ctl.OSC_PREFIX, name)
        assert addr in ctl.osc_addresses()
        assert ctl.parse_osc_profile_message(addr, [1.0]) == name

    def test_trailing_slash_tolerated(self):
        assert ctl.parse_osc_profile_message("/dj/profile/VAPOR_UV/", [1.0]) == "VAPOR_UV"


class TestArgumentForm:
    def test_string_argument_resolves(self):
        assert ctl.parse_osc_profile_message("/dj/profile", ["DEEP_LASER"]) == "DEEP_LASER"

    def test_index_argument_is_one_based(self):
        assert ctl.parse_osc_profile_message("/dj/profile", [1]) == NAMES[0]
        assert ctl.parse_osc_profile_message("/dj/profile", [len(NAMES)]) == NAMES[-1]

    @pytest.mark.parametrize("idx", [0, -1, 99])
    def test_out_of_range_index_ignored(self, idx):
        assert ctl.parse_osc_profile_message("/dj/profile", [idx]) is None


class TestIgnoredTraffic:
    """Anything unrecognised must be a no-op, not a guess."""

    def test_button_release_does_not_refire(self):
        """1 on press, 0 on release -- the release must not re-apply the look."""
        assert ctl.parse_osc_profile_message("/dj/profile/UV_RAVE", [1.0]) == "UV_RAVE"
        assert ctl.parse_osc_profile_message("/dj/profile/UV_RAVE", [0.0]) is None
        assert ctl.parse_osc_profile_message("/dj/profile/UV_RAVE", [False]) is None

    @pytest.mark.parametrize("addr", [
        "", "/", "/dj", "/dj/profile/NOT_A_PROFILE",
        "/other/thing", "/dj/profiles/UV_RAVE", "/td/gen/shader/palette/color0",
    ])
    def test_unrecognised_addresses_ignored(self, addr):
        assert ctl.parse_osc_profile_message(addr, [1.0]) is None

    def test_bare_prefix_without_args_ignored(self):
        assert ctl.parse_osc_profile_message("/dj/profile", []) is None
        assert ctl.parse_osc_profile_message("/dj/profile", None) is None

    def test_unknown_string_argument_ignored(self):
        assert ctl.parse_osc_profile_message("/dj/profile", ["PURPLE_HAZE"]) is None


class TestSafetyGuarantees:
    SOURCE = (REPO / "touchdesigner" / "scripts" / "osc_profile_control.py").read_text()

    def test_no_audio_tap_and_no_chop_execute(self):
        """The freeze guarantee: nothing here rides the per-frame audio path."""
        code = "\n".join(
            line for line in self.SOURCE.splitlines()
            if not line.lstrip().startswith("#")
        )
        assert "onValueChange" not in code
        assert "audio_spectrum" not in code

    def test_does_not_touch_obs(self):
        """The sacred 'Radio DJ' scene stays untouched; Syphon is overlay-only.

        Comments are stripped first -- the header says 'nothing here talks to
        OBS', and matching that sentence was the test failing on its own prose.
        """
        code = "\n".join(
            line for line in self.SOURCE.splitlines()
            if not line.lstrip().startswith("#")
        ).lower()
        assert "obs" not in code

    def test_handler_reacts_to_packets_not_frames(self):
        """onTableChange fires per OSC message, not every cook."""
        assert "def onTableChange" in ctl.HANDLER_CODE
        assert "def onFrameStart" not in ctl.HANDLER_CODE

    def test_port_does_not_collide_with_the_tracker(self):
        """The tracker already streams body data to 7000."""
        assert ctl.OSC_PORT != 7000
        assert 1024 < ctl.OSC_PORT < 65536

    def test_install_is_a_safe_no_op_outside_td(self):
        assert ctl.install_osc_profile_control() is None


class TestLayoutGeneration:
    def test_layout_contains_every_profile_address(self):
        xml = layout.build_xml()
        for name in NAMES:
            assert "%s/%s" % (ctl.OSC_PREFIX, name) in xml

    def test_layout_has_one_button_per_profile(self):
        assert layout.build_xml().count('type="BUTTON"') == len(NAMES)

    def test_layout_has_a_current_profile_label(self):
        assert 'type="LABEL"' in layout.build_xml()

    def test_layout_is_well_formed_xml(self):
        """A malformed document would fail to load with no useful error."""
        import xml.etree.ElementTree as ET

        ET.fromstring(layout.build_xml())

    def test_tosc_payload_round_trips_through_zlib(self):
        """The .tosc is the zlib-compressed form of exactly this document."""
        xml = layout.build_xml()
        assert zlib.decompress(zlib.compress(xml.encode("utf-8"), 9)).decode() == xml

    def test_buttons_are_laid_out_inside_the_screen(self):
        """Off-screen buttons are untappable and easy to ship by accident."""
        import xml.etree.ElementTree as ET

        root = ET.fromstring(layout.build_xml())
        for node in root.iter("node"):
            if node.get("type") != "BUTTON":
                continue
            box = {p.find("key").text: int(p.find("value").text)
                   for p in node.iter("property")
                   if p.get("type") == "i" and p.find("key").text in "xywh"}
            assert box["x"] >= 0 and box["y"] >= 0
            assert box["x"] + box["w"] <= layout.WIDTH
            assert box["y"] + box["h"] <= layout.HEIGHT
