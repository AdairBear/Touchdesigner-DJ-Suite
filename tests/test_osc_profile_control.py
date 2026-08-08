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

import attractor_engine as ae  # noqa: E402
import audience_control as aud  # noqa: E402
import dj_graphics_profiles as gp  # noqa: E402
import osc_profile_control as ctl  # noqa: E402
import make_touchosc_layout as layout  # noqa: E402

NAMES = list(gp.PROFILES)
KNOBS = list(ae.DJ_CHANNELS)


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


def _nodes(ntype, document=None):
    """Collect every node of one control type, in document order.

    Args:
        ntype: BUTTON, FADER, LABEL or GROUP.
        document: Layout XML to read. Defaults to the full generated layout.

    Returns:
        A list of <node> elements.
    """
    import xml.etree.ElementTree as ET

    root = _tree() if document is None else ET.fromstring(document)
    return [n for n in root.iter("node") if n.get("type") == ntype]


def _name(node):
    """Read a node's name property.

    Args:
        node: A <node> element.

    Returns:
        The name string.
    """
    return node.find("properties/property[key='name']/value").text


def _profile_buttons():
    """Collect only the profile-grid buttons.

    The strip added PANIC, the knob reset and the audience switch to the
    document, so "every BUTTON" is no longer "every profile".

    Returns:
        A list of <node> elements, in registry order.
    """
    return [n for n in _nodes("BUTTON") if _name(n) in set(NAMES)]


def _address(node):
    """Reconstruct a control's OSC address from its path partials.

    A substring check against the raw document would pass on a <path> that was
    a literal string -- exactly the shape TouchOSC ignores -- so every address
    assertion goes through here.

    Args:
        node: A BUTTON or FADER <node>.

    Returns:
        The address as a string.
    """
    return "".join(p.find("value").text
                   for p in node.findall("messages/osc/path/partial"))


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
        built = {_address(node) for node in _profile_buttons()}
        assert built == set(ctl.osc_addresses())

    def test_layout_has_one_button_per_profile(self):
        assert len(_profile_buttons()) == len(NAMES)

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
        """Every control, strip included -- one frameless node draws nothing.

        Counted rather than merely iterated: the root, the page title, the
        strip caption, a button+caption per profile, a fader+caption per
        continuous control, and a button+caption per action. A count is what
        catches a section that silently emitted nothing at all.
        """
        controls = (len(NAMES)
                    + len(layout.attractor_faders())
                    + len(layout.audience_faders())
                    + len(layout.actions()))
        nodes = list(_tree().iter("node"))
        assert len(nodes) == 1 + 2 + (2 * controls)
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

    def test_buttons_are_fat_targets_that_never_overlap(self):
        """Fat targets a thumb can hit in a dark booth, however many there are.

        The registry outgrew one column when the attractor looks landed, so the
        assertion is the ergonomic invariant rather than the old single-column
        geometry: every button clears the thumb minimum, none overlaps another,
        and none escapes the frame. `_grid` adds a column instead of shrinking
        a target, and this is what holds it to that.

        The strip's action buttons are in scope here on purpose. PANIC is the
        one control on the page that gets pressed without being looked at.
        """
        rects = [_frame(node) for node in _nodes("BUTTON")]
        assert rects, "no buttons in the layout"
        for x, y, w, h in rects:
            assert h >= layout.MIN_BUTTON_H
            assert w >= layout.MIN_BUTTON_H, "a target this narrow is a miss"
            assert x >= layout.MARGIN
            assert x + w <= layout.WIDTH - layout.MARGIN
            assert y + h <= layout.HEIGHT - layout.MARGIN
        for i, (ax, ay, aw, ah) in enumerate(rects):
            for bx, by, bw, bh in rects[i + 1:]:
                overlaps = (ax < bx + bw and bx < ax + aw
                            and ay < by + bh and by < ay + ah)
                assert not overlaps, "buttons overlap: %s vs %s" % (
                    (ax, ay, aw, ah), (bx, by, bw, bh))

    def test_a_single_column_still_spans_the_full_width(self):
        """The one-column case is unchanged -- five profiles laid out as before.

        The strip took height off this grid's budget, so five buttons are
        shorter than they were. The invariant was never the pixel count: it is
        one full-width column that still clears the thumb minimum, and that is
        what is asserted.
        """
        cols, btn_w, btn_h = layout._grid(5)
        assert cols == 1
        assert btn_w == layout.WIDTH - 2 * layout.MARGIN
        assert btn_h >= layout.MIN_BUTTON_H


class TestButtonsMatchTouchOscSchema:
    """The button node shape, checked against a real editor-produced layout."""

    def test_buttons_are_momentary_and_interactive(self):
        """Every button is momentary except the audience switch.

        That one is a toggle because `audience_control.route` reads its VALUE
        rather than treating it as a press: a momentary switch there would
        enable the room and disable it again on the lift.
        """
        toggles = {a.name for a in layout.actions()
                   if a.button_type == layout.BUTTON_TOGGLE}
        for node in _nodes("BUTTON"):
            props = {p.find("key").text: p.find("value").text
                     for p in node.iter("property")}
            expected = ("1" if _name(node) in toggles else "0")
            assert props["buttonType"] == expected
            assert props["interactive"] == "1"
            assert props["press"] == "1" and props["release"] == "1"

    def test_buttons_declare_the_touch_and_x_values(self):
        for node in _nodes("BUTTON"):
            keys = {v.find("key").text for v in node.find("values")}
            assert keys == {"touch", "x"}

    @pytest.mark.parametrize("index,name", list(enumerate(NAMES)), ids=NAMES)
    def test_button_path_partials_concatenate_to_its_address(self, index, name):
        """The address is built from <partial> elements, never a literal string."""
        osc = _profile_buttons()[index].find("messages/osc")
        assert osc is not None
        partials = osc.findall("path/partial")
        assert partials, "an <osc> with no path partials sends to nothing"
        assert all(p.find("type").text == "CONSTANT" for p in partials)
        joined = "".join(p.find("value").text for p in partials)
        assert joined == "%s/%s" % (ctl.OSC_PREFIX, name)

    @pytest.mark.parametrize("index,name", list(enumerate(NAMES)), ids=NAMES)
    def test_button_sends_one_float_argument_from_its_x_value(self, index, name):
        """1 on press, 0 on release -- the handler ignores the 0."""
        osc = _profile_buttons()[index].find("messages/osc")
        args = osc.findall("arguments/partial")
        assert len(args) == 1
        assert args[0].find("type").text == "VALUE"
        assert args[0].find("conversion").text == "FLOAT"
        assert args[0].find("value").text == "x"

    def test_messages_are_enabled_sending_on_connection_one(self):
        for node in _nodes("BUTTON") + _nodes("FADER"):
            osc = node.find("messages/osc")
            assert osc.find("enabled").text == "1"
            assert osc.find("send").text == "1"
            assert osc.find("connections").text == "00001"

    def test_nothing_on_the_page_listens(self):
        """Send-only. A pad the show can reposition is a pad he cannot trust."""
        for node in _nodes("BUTTON") + _nodes("FADER"):
            osc = node.find("messages/osc")
            assert osc.find("receive").text == "0"
            assert osc.find("feedback").text == "0"


class TestCaptions:
    """Buttons render no text of their own, so each caption is a LABEL."""

    def test_every_button_has_a_caption_reading_its_profile_name(self):
        captions = [lb.find("values/value[key='text']/default").text
                    for lb in _nodes("LABEL")]
        head = ["DJ PROFILES"] + [n.replace("_", " ") for n in NAMES]
        assert captions[:len(head)] == head

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
        """Matched by NAME, not by position -- the strip interleaves types.

        A fader's caption deliberately covers only the bottom sliver of it, so
        it is checked for containment rather than for an exact match.
        """
        frames = {_name(n): _frame(n) for n in _nodes("BUTTON") + _nodes("FADER")}
        labels = {_name(n): _frame(n) for n in _nodes("LABEL")}
        for name, rect in frames.items():
            caption = labels.get("%s_text" % name)
            assert caption is not None, "%s has no caption" % name
            cx, cy, cw, ch = caption
            x, y, w, h = rect
            assert (x <= cx and y <= cy
                    and cx + cw <= x + w and cy + ch <= y + h), name

    def test_caption_is_drawn_after_its_button(self):
        """Later siblings draw on top; a caption behind its control is invisible."""
        order = [n.get("type") for n in _tree()[0].find("children")]
        controls = (len(NAMES) + len(layout.attractor_faders())
                    + len(layout.audience_faders()) + len(layout.actions()))
        # One page title, one strip caption, and a control/caption pair each.
        assert order.count("LABEL") == 2 + controls
        for index, kind in enumerate(order):
            if kind in ("BUTTON", "FADER"):
                assert order[index + 1] == "LABEL", (
                    "control at %d has no caption drawn over it" % index)


class TestControlChannelsAreReadLive:
    """The lockstep: every capability's address reaches the iPad.

    This is the regression suite for the growth defect. Before it, the
    generator emitted profile buttons only, so the attractor knobs and PANIC
    were hand-added in the TouchOSC editor and destroyed by the next
    regeneration -- a capability that existed in TouchDesigner but had no
    button on the pad. These tests fail on that generator.

    They assert against the OWNING modules, never against a list written here.
    A knob added to attractor_engine.DJ_CHANNELS must appear on the pad, and
    the way that is enforced is by deriving the expectation from DJ_CHANNELS.
    """

    def test_every_attractor_knob_has_a_fader(self):
        built = {_address(node) for node in _nodes("FADER")}
        for channel in KNOBS:
            assert "%s/%s" % (ctl.ATTRACTOR_PREFIX, channel) in built

    def test_a_new_knob_would_be_reachable_without_editing_the_generator(self):
        """The lockstep itself, exercised rather than asserted about.

        DJ_CHANNELS is patched and the layout rebuilt; if the generator kept
        its own list of knobs the new one would simply not appear.
        """
        original = ae.DJ_CHANNELS
        try:
            ae.DJ_CHANNELS = tuple(original) + ("warp",)
            built = {_address(n) for n in _nodes("FADER", layout.build_xml())}
            assert "%s/warp" % ctl.ATTRACTOR_PREFIX in built
        finally:
            ae.DJ_CHANNELS = original
        # ...and it is gone again, so the suite has not poisoned itself.
        assert "%s/warp" % ctl.ATTRACTOR_PREFIX not in {
            _address(n) for n in _nodes("FADER")}

    def test_panic_is_on_the_pad(self):
        """The one control whose absence is not a missing feature but a risk."""
        built = {_address(node): node for node in _nodes("BUTTON")}
        assert aud.PANIC_ADDRESS in built
        panic = built[aud.PANIC_ADDRESS]
        x, y, w, h = _frame(panic)
        assert h >= layout.MIN_BUTTON_H and w >= layout.MIN_ACTION_W

    def test_panic_is_momentary_so_one_press_is_one_packet(self):
        """audience_control.route needs a PRESS; a toggle would arm it wrong."""
        panic = next(n for n in _nodes("BUTTON")
                     if _address(n) == aud.PANIC_ADDRESS)
        props = {p.find("key").text: p.find("value").text
                 for p in panic.iter("property")}
        assert props["buttonType"] == str(layout.BUTTON_MOMENTARY)

    def test_the_knob_reset_is_on_the_pad(self):
        built = {_address(node) for node in _nodes("BUTTON")}
        assert "%s/reset" % ctl.ATTRACTOR_PREFIX in built

    def test_audience_enable_and_gain_are_on_the_pad(self):
        known = set(aud.audience_addresses())
        built = {_address(n) for n in _nodes("BUTTON") + _nodes("FADER")}
        for control in ("enable", "gain"):
            address = "%s/%s" % (aud.AUDIENCE_PREFIX, control)
            if address in known:
                assert address in built, "%s exists but is unreachable" % address

    def test_audience_controls_are_skipped_when_the_module_drops_them(self):
        """Presence is read, not assumed -- so a removal does not emit a dead
        control that sends into nothing."""
        original = aud.audience_addresses
        try:
            aud.audience_addresses = lambda: [aud.PANIC_ADDRESS]
            built = {_address(n) for n in
                     _nodes("BUTTON", layout.build_xml())
                     + _nodes("FADER", layout.build_xml())}
            assert "%s/gain" % aud.AUDIENCE_PREFIX not in built
            assert "%s/enable" % aud.AUDIENCE_PREFIX not in built
            assert aud.PANIC_ADDRESS in built
        finally:
            aud.audience_addresses = original

    def test_no_control_sends_an_address_nothing_accepts(self):
        """The other direction: a button wired to an address no handler parses
        is a button that does nothing, which is worse than a missing one."""
        for node in _nodes("BUTTON") + _nodes("FADER"):
            address = _address(node)
            accepted = (
                ctl.parse_osc_profile_message(address, [1.0]) is not None
                or ctl.parse_osc_attractor_message(address, [1.0]) is not None
                or aud.parse_audience_message(address, [1.0]) is not None)
            assert accepted, "%s (%s) sends to nothing" % (_name(node), address)

    def test_layout_addresses_reports_exactly_what_the_document_sends(self):
        """The printed report and the document cannot drift apart."""
        built = [_address(n) for n in _nodes("BUTTON") + _nodes("FADER")]
        assert sorted(built) == sorted(layout.layout_addresses())


class TestKnobFadersSendTheRightRange:
    """A knob is a bounded -1..1 OFFSET, and the fader must say so."""

    def test_knob_faders_scale_their_travel_to_minus_one_to_one(self):
        for node in _nodes("FADER"):
            if not _address(node).startswith(ctl.ATTRACTOR_PREFIX + "/"):
                continue
            arg = node.find("messages/osc/arguments/partial")
            assert float(arg.find("scaleMin").text) == -1.0
            assert float(arg.find("scaleMax").text) == 1.0

    def test_knob_faders_rest_at_zero_offset(self):
        """Centre is the resting state, and it is a position a thumb can find.

        A knob resting at an end stop would apply a full-span offset the moment
        the layout loads, so the show would come up already pushed.
        """
        for node in _nodes("FADER"):
            if not _address(node).startswith(ctl.ATTRACTOR_PREFIX + "/"):
                continue
            handle = float(node.find("values/value[key='x']/default").text)
            assert handle == 0.5
            # And what that handle position actually sends is zero.
            arg = node.find("messages/osc/arguments/partial")
            lo = float(arg.find("scaleMin").text)
            hi = float(arg.find("scaleMax").text)
            assert lo + handle * (hi - lo) == 0.0

    def test_the_engine_accepts_both_ends_of_every_knob_fader(self):
        """Travel checked against the parser, not against a number here."""
        for node in _nodes("FADER"):
            address = _address(node)
            if not address.startswith(ctl.ATTRACTOR_PREFIX + "/"):
                continue
            for sent in (-1.0, -0.37, 1.0):
                command = ctl.parse_osc_attractor_message(address, [sent])
                assert command is not None
                assert command["value"] == pytest.approx(sent)

    def test_the_gain_fader_rests_where_the_show_actually_starts(self):
        """AudienceState.gain defaults to 1.0; a fader resting elsewhere lies."""
        gain = "%s/gain" % aud.AUDIENCE_PREFIX
        if gain not in set(aud.audience_addresses()):
            pytest.skip("audience gain is not offered by audience_control")
        node = next(n for n in _nodes("FADER") if _address(n) == gain)
        assert float(node.find("values/value[key='x']/default").text) == \
            aud.AudienceState().gain
        arg = node.find("messages/osc/arguments/partial")
        assert float(arg.find("scaleMin").text) == 0.0
        assert float(arg.find("scaleMax").text) == 1.0


class TestRegenerationLosesNothing:
    """The defect in one sentence: regenerating used to destroy hand-added
    controls. It cannot now, because there is nothing hand-added to destroy."""

    def test_regeneration_is_byte_for_byte_stable(self):
        """Deterministic node IDs -- a re-run is diffable, not noise."""
        assert layout.build_xml() == layout.build_xml()

    def test_a_regeneration_cycle_keeps_every_capability_reachable(self):
        """Generate, 'ship it', regenerate: the surface is complete both times.

        This is the assertion the old generator could not make. Its second
        pass produced a document with the knobs and PANIC missing, because
        they had only ever existed in the editor.
        """
        required = set(layout.layout_addresses())
        for _ in range(2):
            document = layout.build_xml()
            built = {_address(n) for n in _nodes("BUTTON", document)
                     + _nodes("FADER", document)}
            assert required <= built
            for channel in KNOBS:
                assert "%s/%s" % (ctl.ATTRACTOR_PREFIX, channel) in built
            assert aud.PANIC_ADDRESS in built

    def test_the_fallback_document_is_the_pre_strip_layout(self):
        """FADER is the one unverified node type, so a fader-free copy ships too.

        It carries every profile and no fader, which is exactly what makes it
        usable if the full layout will not render on the device.
        """
        document = layout.build_xml(include_strip=False)
        assert not _nodes("FADER", document)
        built = {_address(n) for n in _nodes("BUTTON", document)}
        assert built == set(ctl.osc_addresses())

    def test_the_fallback_gives_the_profile_grid_its_old_height_back(self):
        """With no strip to make room for, the buttons are the taller ones."""
        full = [_frame(n) for n in _profile_buttons()]
        fallback = [_frame(n) for n in _nodes("BUTTON",
                                              layout.build_xml(include_strip=False))]
        assert fallback[0][3] > full[0][3]
        for x, y, w, h in fallback:
            assert h >= layout.MIN_BUTTON_H
            assert y + h <= layout.HEIGHT - layout.MARGIN


class TestStripGeometry:
    """The strip has to fit, and it has to keep fitting as registries grow."""

    def test_the_strip_and_the_grid_do_not_collide(self):
        grid_bottom = max(y + h for _, y, _, h in
                          (_frame(n) for n in _profile_buttons()))
        strip_top = layout.HEIGHT - layout.MARGIN - layout.strip_height()
        assert grid_bottom <= strip_top

    def test_the_strip_ends_at_the_bottom_margin(self):
        """Computed, not hand-tuned: a strip that overruns clips PANIC."""
        bottom = max(y + h for _, y, _, h in
                     (_frame(n) for n in _nodes("BUTTON") + _nodes("FADER")))
        assert bottom == layout.HEIGHT - layout.MARGIN

    def test_faders_are_wide_enough_to_drag(self):
        for node in _nodes("FADER"):
            _, _, w, h = _frame(node)
            assert w >= layout.MIN_FADER_W
            assert h == layout.STRIP_FADER_H

    def test_faders_wrap_to_a_second_row_instead_of_going_thin(self):
        """Same rule the profile grid follows: hold the target size, take a row."""
        total_w = layout.WIDTH - 2 * layout.MARGIN
        one_row, single_w = layout._row_split(12, total_w, layout.MIN_FADER_W,
                                              max_rows=1)
        assert single_w < layout.MIN_FADER_W, "premise: 12 will not fit in one row"
        rows, width = layout._row_split(12, total_w, layout.MIN_FADER_W)
        assert one_row == 1 and rows == 2
        assert width >= layout.MIN_FADER_W

    def test_the_row_cap_is_a_hard_stop_not_a_silent_shrink(self):
        """Past what two rows can hold, the cap wins and cells go under the
        minimum. That is a deliberate ceiling -- an unbounded strip would eat
        the profile grid -- and it is asserted so it stays a known trade rather
        than a surprise the night it happens.
        """
        rows, width = layout._row_split(40, layout.WIDTH - 2 * layout.MARGIN,
                                        layout.MIN_FADER_W)
        assert rows == 2, "the cap holds"
        assert width < layout.MIN_FADER_W, "and the cost is thin cells"

    def test_a_grown_knob_registry_still_lays_out_inside_the_page(self):
        """Eight knobs is a plausible near-future; it must not run off the page."""
        original = ae.DJ_CHANNELS
        try:
            ae.DJ_CHANNELS = tuple(original) + ("warp", "bloom", "fold")
            document = layout.build_xml()
            for node in _nodes("BUTTON", document) + _nodes("FADER", document):
                x, y, w, h = _frame(node)
                assert x >= layout.MARGIN and y >= layout.MARGIN
                assert x + w <= layout.WIDTH - layout.MARGIN
                assert y + h <= layout.HEIGHT - layout.MARGIN
        finally:
            ae.DJ_CHANNELS = original
