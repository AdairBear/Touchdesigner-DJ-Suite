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


def _tree():
    """Parse the generated layout.

    Returns:
        The <lexml> root element.
    """
    import xml.etree.ElementTree as ET

    return ET.fromstring(layout.build_xml())


def _nodes(ntype):
    """Collect every node of one control type, in document order.

    Args:
        ntype: BUTTON, LABEL or GROUP.

    Returns:
        A list of <node> elements.
    """
    return [n for n in _tree().iter("node") if n.get("type") == ntype]


def _frame(node):
    """Read a node's geometry.

    Args:
        node: A <node> element.

    Returns:
        (x, y, w, h) as ints.

    Raises:
        AssertionError: If the node has no frame -- the defect that shipped an
            empty layout to the iPad.
    """
    value = node.find("properties/property[@type='r'][key='frame']/value")
    assert value is not None, "node has no frame property"
    return tuple(int(value.find(k).text) for k in "xywh")


class TestLayoutGeneration:
    def test_layout_contains_every_profile_address(self):
        """Addresses are assembled from partials, so reconstruct before asserting.

        A substring check would pass on a document whose <path> was a literal
        string -- exactly the shape TouchOSC ignores.
        """
        built = {"".join(p.find("value").text
                         for p in node.findall("messages/osc/path/partial"))
                 for node in _nodes("BUTTON")}
        assert built == set(ctl.osc_addresses())

    def test_layout_has_one_button_per_profile(self):
        assert layout.build_xml().count('type="BUTTON"') == len(NAMES)

    def test_layout_is_well_formed_xml(self):
        """A malformed document would fail to load with no useful error."""
        _tree()

    def test_document_is_a_lexml_version_3_with_one_root_group(self):
        """The container TouchOSC expects. Anything else opens as nothing."""
        root = _tree()
        assert root.tag == "lexml"
        assert root.get("version") == "3"
        assert len(root) == 1 and root[0].get("type") == "GROUP"

    def test_tosc_payload_round_trips_through_zlib(self):
        """The .tosc is the zlib-compressed form of exactly this document."""
        xml = layout.build_xml()
        packed = zlib.compress(xml.encode("utf-8"), layout.ZLIB_LEVEL)
        assert zlib.decompress(packed).decode() == xml
        assert packed[:2] == b"\x78\x9c", "TouchOSC's own exporter writes 78 9c"


class TestEveryControlIsVisible:
    """Regression guard for the empty-layout defect.

    The first generated .tosc gave each node four separate integer x/y/w/h
    properties. TouchOSC's geometry lives in ONE rect property keyed 'frame';
    with none present every control had no size and the layout opened blank.
    These tests fail on that document and pass on the corrected one.
    """

    def test_every_node_has_a_rect_frame(self):
        nodes = list(_tree().iter("node"))
        assert len(nodes) == 1 + 1 + (2 * len(NAMES))
        for node in nodes:
            _frame(node)

    def test_no_node_carries_the_invented_int_geometry(self):
        """x/y/w/h as separate int properties is the bug's fingerprint."""
        for node in _tree().iter("node"):
            keys = {p.find("key").text for p in node.iter("property")
                    if p.get("type") == "i"}
            assert not (keys & {"x", "y", "w", "h"})

    def test_every_control_is_marked_visible(self):
        for node in _tree().iter("node"):
            assert node.find("properties/property[key='visible']/value").text == "1"

    def test_buttons_are_laid_out_inside_the_screen(self):
        """Off-screen buttons are untappable and easy to ship by accident."""
        for node in _nodes("BUTTON"):
            x, y, w, h = _frame(node)
            assert x >= 0 and y >= 0
            assert x + w <= layout.WIDTH
            assert y + h <= layout.HEIGHT

    def test_buttons_are_full_width_and_stacked_without_overlap(self):
        """Five fat targets a thumb can hit in a dark booth."""
        bottom = 0
        for node in _nodes("BUTTON"):
            x, y, w, h = _frame(node)
            assert w == layout.WIDTH - 2 * layout.MARGIN
            assert h >= 120
            assert y >= bottom
            bottom = y + h


class TestButtonsMatchTouchOscSchema:
    """The button node shape, checked against a real editor-produced layout."""

    def test_buttons_are_momentary_and_interactive(self):
        for node in _nodes("BUTTON"):
            props = {p.find("key").text: p.find("value").text
                     for p in node.iter("property")}
            assert props["buttonType"] == "0", "Momentary"
            assert props["interactive"] == "1"
            assert props["press"] == "1" and props["release"] == "1"

    def test_buttons_declare_the_touch_and_x_values(self):
        for node in _nodes("BUTTON"):
            keys = {v.find("key").text for v in node.find("values")}
            assert keys == {"touch", "x"}

    @pytest.mark.parametrize("index,name", list(enumerate(NAMES)), ids=NAMES)
    def test_button_path_partials_concatenate_to_its_address(self, index, name):
        """The address is built from <partial> elements, never a literal string."""
        osc = _nodes("BUTTON")[index].find("messages/osc")
        assert osc is not None
        partials = osc.findall("path/partial")
        assert partials, "an <osc> with no path partials sends to nothing"
        assert all(p.find("type").text == "CONSTANT" for p in partials)
        joined = "".join(p.find("value").text for p in partials)
        assert joined == "%s/%s" % (ctl.OSC_PREFIX, name)

    @pytest.mark.parametrize("index,name", list(enumerate(NAMES)), ids=NAMES)
    def test_button_sends_one_float_argument_from_its_x_value(self, index, name):
        """1 on press, 0 on release -- the handler ignores the 0."""
        osc = _nodes("BUTTON")[index].find("messages/osc")
        args = osc.findall("arguments/partial")
        assert len(args) == 1
        assert args[0].find("type").text == "VALUE"
        assert args[0].find("conversion").text == "FLOAT"
        assert args[0].find("value").text == "x"

    def test_messages_are_enabled_sending_on_connection_one(self):
        for node in _nodes("BUTTON"):
            osc = node.find("messages/osc")
            assert osc.find("enabled").text == "1"
            assert osc.find("send").text == "1"
            assert osc.find("connections").text == "00001"


class TestCaptions:
    """Buttons render no text of their own, so each caption is a LABEL."""

    def test_every_button_has_a_caption_reading_its_profile_name(self):
        captions = [lb.find("values/value[key='text']/default").text
                    for lb in _nodes("LABEL")]
        assert captions == ["DJ PROFILES"] + [n.replace("_", " ") for n in NAMES]

    def test_captions_are_pinned_so_they_survive_load(self):
        for label in _nodes("LABEL"):
            text = label.find("values/value[key='text']")
            assert text.find("lockedDefaultCurrent").text == "1"

    def test_captions_do_not_swallow_the_tap(self):
        """A caption sits on top of its button; it must not be interactive."""
        for label in _nodes("LABEL"):
            props = {p.find("key").text: p.find("value").text
                     for p in label.iter("property")}
            assert props["interactive"] == "0"
            assert props["background"] == "0"

    def test_each_caption_covers_exactly_its_button(self):
        buttons = _nodes("BUTTON")
        captions = _nodes("LABEL")[1:]  # index 0 is the title
        for button, caption in zip(buttons, captions):
            assert _frame(button) == _frame(caption)

    def test_caption_is_drawn_after_its_button(self):
        """Later siblings draw on top; a caption behind its button is invisible."""
        order = [n.get("type") for n in _tree()[0].find("children")]
        assert order == ["LABEL"] + ["BUTTON", "LABEL"] * len(NAMES)
