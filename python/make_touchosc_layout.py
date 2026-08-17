#!/usr/bin/env python3
"""Generate the TouchOSC layout for live graphics-profile switching.

FORMAT NOTE -- READ THIS
    A modern TouchOSC (Hexler, "next-gen", v1.x) ``.tosc`` file is a raw zlib
    stream wrapping one XML document. The schema was verified against an
    authentic editor-produced layout, not guessed:

        <lexml version="3">
          <node ID="<uuid>" type="GROUP">
            <properties>  <!-- geometry is ONE rect property, key "frame" -->
              <property type="r"><key>frame</key>
                <value><x/><y/><w/><h/></value></property>
              ...
            </properties>
            <values>      <!-- per-control state: touch, x, text -->
            <messages>    <!-- <osc> with <path>/<arguments> built from
                               <partial> elements, never a literal string -->
            <children>    <!-- GROUP only -->

    The previous version of this script invented a schema (separate int x/y/w/h
    properties, a literal <path> string, <argument> elements, text on buttons).
    TouchOSC parsed it, found no frame on any node, and drew an empty layout.

    Host and send port are NOT stored in the document -- TouchOSC keeps
    connection settings outside the layout. Port 7400 must be entered once on
    each device (Connections -> OSC -> Connection 1). See
    docs/touchosc_profile_control.md.

EVERY CONTROL CHANNEL IS READ LIVE -- THIS IS THE POINT OF THE FILE
    Nothing here keeps its own list of what the show can do. The document is
    assembled from the modules that OWN each namespace:

        profiles   dj_graphics_profiles.PROFILES
        knobs      attractor_engine.DJ_CHANNELS  (via osc_profile_control)
        reset      osc_profile_control.ATTRACTOR_PREFIX
        panic      audience_control.PANIC_ADDRESS
        audience   audience_control.audience_addresses()  -- enable / gain

    The reason is a failure mode, not tidiness. Before this, the generator knew
    only about profiles, so the attractor knobs and PANIC were hand-added in
    the TouchOSC editor -- and every regeneration silently destroyed them. A
    capability that exists in TouchDesigner but has no button is not reachable
    mid-set, and the newest capability is the one most likely to need a hand on
    it. Adding a knob to DJ_CHANNELS must put a fader on the iPad, or the
    control surface falls behind the palette again.

    The imports below are deliberately unguarded. A missing module is a loud
    ImportError, not a layout that quietly comes out one section short.

NODE TYPES -- WHAT IS VERIFIED AND WHAT IS NOT
    GROUP / BUTTON / LABEL are checked against an authentic editor-produced
    layout. FADER is NOT -- no reference file on this machine contains one, so
    its type-specific properties (``response``, ``bar``, ``centered``, ...) and
    the toggle ``buttonType`` value are reasoned, not verified.

    That is why ``main`` also writes DJ_Profiles_profiles_only.tosc: the exact
    document that shipped before, with no fader in it. If the full layout mis-
    renders in the editor or on the iPad, that file is the known-good fallback
    and the set still has its profile buttons. See the verification note in
    docs/touchosc_profile_control.md.

USAGE
    ./venv/bin/python python/make_touchosc_layout.py
"""

from __future__ import annotations

import os
import sys
import uuid
import zlib
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "touchdesigner", "scripts"))

import attractor_engine as ae  # noqa: E402
import audience_control as aud  # noqa: E402
import dj_graphics_profiles as gp  # noqa: E402
import osc_profile_control as ctl  # noqa: E402

#: AirDrop target. ~/Desktop so it is trivial to find and send to both devices.
OUT_DIR = os.path.expanduser("~/Desktop")
BASENAME = "DJ_Profiles"
#: Fallback document: profile buttons only, no unverified node type in it.
FALLBACK_SUFFIX = "_profiles_only"

#: Layout geometry, sized for an iPhone screen so it also works on an iPad.
WIDTH, HEIGHT = 720, 1280
MARGIN, GAP = 40, 24
LABEL_H = 90

#: Smallest button a thumb can reliably hit in a dark booth, in points. This is
#: the constraint the grid is solved for -- it is not negotiable downward, so
#: when the registry outgrows one column the layout adds a column rather than
#: shrinking the targets. See `_grid`.
MIN_BUTTON_H = 120
#: Two columns fit a 720 pt tablet comfortably. Three would put the targets
#: back under the thumb minimum horizontally, which defeats the point.
MAX_COLUMNS = 2

# --- The live-control strip -------------------------------------------------
# A fixed band along the bottom of the same 720x1280 page. It is a band and not
# a second page because a knob you have to navigate to is a knob you will not
# reach at 02:00 -- and because a PAGER is a structure no reference file here
# can confirm, which is how the empty-layout defect happened the first time.
#
# The strip takes its height off the top of the profile grid's budget. That is
# the whole trade: five profiles in one column now get 124 pt buttons instead
# of 217 pt ones. Both clear MIN_BUTTON_H, and `_grid` still adds a column
# rather than going under it.

#: Inner gap inside the strip. Tighter than GAP: these rows are one instrument.
STRIP_GAP = 12
#: Section caption height ("LIVE CONTROL").
STRIP_LABEL_H = 30
#: Fader body height. A 170 pt throw is enough travel to ride a knob.
STRIP_FADER_H = 170
#: Action buttons (RESET / AUDIENCE / PANIC) get the full thumb minimum. PANIC
#: especially: it is pressed in a hurry, in the dark, by someone not looking.
STRIP_ACTION_H = MIN_BUTTON_H
#: Narrowest fader worth dragging. Faders wrap to a second row below this, the
#: same way the profile grid takes a column rather than shrinking a target.
MIN_FADER_W = 72
#: Narrowest action button. Below this they wrap too.
MIN_ACTION_W = 150

#: zlib level TouchOSC's own exporter uses -- its files begin 78 9c.
ZLIB_LEVEL = 6

#: Namespace for deterministic node IDs -- regenerating gives the same document
#: byte-for-byte, so a re-run is diffable instead of noise.
_NS = uuid.UUID("6f1a0c2e-0000-4000-8000-000000000000")

#: Button fill colours, chosen to echo each profile's own palette so the pad
#: reads at a glance in a dark booth. RGBA floats, TouchOSC's own format.
COLOURS: Dict[str, Tuple[float, float, float, float]] = {
    "UV_RAVE": (1.0, 0.0, 1.0, 1.0),
    "DEEP_LASER": (0.1, 0.35, 1.0, 1.0),
    "STROBE_ACID": (0.35, 1.0, 0.06, 1.0),
    "VAPOR_UV": (1.0, 0.06, 0.55, 1.0),
    "MONO_PULSE": (0.0, 1.0, 1.0, 1.0),
    # The attractor looks, echoing their own palettes the same way.
    "ATTRACTOR": (0.35, 0.45, 1.0, 1.0),
    "ATTRACTOR_LORENZ": (0.1, 0.6, 1.0, 1.0),
    "ATTRACTOR_AIZAWA": (1.0, 0.1, 0.7, 1.0),
}

_WHITE = (1.0, 1.0, 1.0, 1.0)
_BLACK = (0.0, 0.0, 0.0, 1.0)

#: Strip colours. Deliberately NOT profile colours -- a control that changes a
#: look must not read as a look, or a panicking hand grabs the wrong thing.
KNOB_COLOUR = (0.35, 0.45, 1.0, 1.0)        # the attractor's own blue
AUDIENCE_COLOUR = (1.0, 0.65, 0.0, 1.0)     # amber: the room, not Thomas
RESET_COLOUR = (0.35, 0.35, 0.40, 1.0)      # inert grey
PANIC_COLOUR = (1.0, 0.10, 0.10, 1.0)       # the only red on the page

#: How each BARE audience control is drawn -- the operator's own switches over
#: the room (`/dj/audience/<name>`), as distinct from the verbs the audience
#: itself sends (`/dj/audience/profile|nudge|oneshot/...`). Those arrive from
#: the chat bridge and are deliberately NOT on this pad: they are the room's
#: input, not Thomas's, and a button that fakes an audience vote would make the
#: operator indistinguishable from the crowd in the arbiter's own logs.
#:
#: `audience_control.audience_addresses` owns WHICH controls exist. These two
#: tables own only how one is DRAWN. A bare control present there and in
#: neither table raises in `_bare_controls` rather than being skipped -- the
#: same reasoning as the unguarded imports at the top of this file. Silently
#: skipping is exactly the growth defect this generator was rewritten to end.
#:
#: name -> (caption, resting handle position, scale_min, scale_max)
CONTROL_FADERS: Dict[str, Tuple[str, str, float, float]] = {
    # Rests at 1.0 -- AudienceState.gain defaults to 1.0, so the pad and the
    # show agree at startup instead of the fader lying until it is first moved.
    "gain": ("CROWD GAIN", "1.0", 0.0, 1.0),
}
#: name -> (caption, serialised default). Defaults mirror AudienceState's own,
#: so a freshly loaded pad tells the truth about the show it is pointed at.
CONTROL_TOGGLES: Dict[str, Tuple[str, str]] = {
    "enable": ("CROWD ON", "1"),
    # AudienceState.lock_profile defaults to False, so this ships off. It is
    # the graduated response PANIC is not: the room keeps NUDGE and ONESHOT and
    # loses only PROFILE, so a look Thomas has committed to stops being voted
    # out from under him without killing audience interaction outright.
    "lock_profile": ("LOCK LOOK", "0"),
}

#: buttonType values. 0 (Momentary) is confirmed against an authentic layout;
#: every profile button has shipped with it. 1 (Toggle) is NOT confirmed -- it
#: is used only by the audience enable switch, and it is the first thing to
#: check in the editor. A momentary switch there would send 1 then immediately
#: 0, i.e. turn the audience on and straight back off.
BUTTON_MOMENTARY = 0
BUTTON_TOGGLE = 1


# --- XML primitives ---------------------------------------------------------
# Each helper emits exactly the element shape an authentic .tosc uses.

def _nid(tag: str) -> str:
    """Build a stable UUID node ID.

    Args:
        tag: Anything unique within the document.

    Returns:
        A UUID string, the ID form TouchOSC's own editor writes.
    """
    return str(uuid.uuid5(_NS, tag))


def _prop(ptype: str, key: str, value: str) -> str:
    """Build a scalar <property>.

    Args:
        ptype: TouchOSC property type -- s, b, i, f.
        key: Property name.
        value: Serialised value.

    Returns:
        One <property> element.
    """
    return ('<property type="%s"><key>%s</key><value>%s</value></property>'
            % (ptype, key, escape(value)))


def _prop_frame(x: int, y: int, w: int, h: int) -> str:
    """Build the rect <property> that gives a control its geometry.

    This is the single most important element in the document: a node without
    a ``frame`` has no size and never appears on screen.

    Args:
        x: Left edge, relative to the parent node.
        y: Top edge, relative to the parent node.
        w: Width in points.
        h: Height in points.

    Returns:
        One <property type="r"> element.
    """
    return ('<property type="r"><key>frame</key><value>'
            "<x>%d</x><y>%d</y><w>%d</w><h>%d</h>"
            "</value></property>" % (x, y, w, h))


def _prop_colour(key: str, rgba: Sequence[float]) -> str:
    """Build a colour <property>.

    Args:
        key: Property name, e.g. ``color`` or ``textColor``.
        rgba: Four floats in 0..1.

    Returns:
        One <property type="c"> element.
    """
    return ('<property type="c"><key>%s</key><value>'
            "<r>%g</r><g>%g</g><b>%g</b><a>%g</a>"
            "</value></property>" % (key, rgba[0], rgba[1], rgba[2], rgba[3]))


def _value(key: str, default: str, locked_default_current: str = "0") -> str:
    """Build one <value>, the element holding a control's live state.

    Args:
        key: ``touch``, ``x`` or ``text``.
        default: Serialised default.
        locked_default_current: "1" pins the default as the current value --
            how a static label stores its caption.

    Returns:
        One <value> element.
    """
    return ("<value><key>%s</key><locked>0</locked>"
            "<lockedDefaultCurrent>%s</lockedDefaultCurrent>"
            "<default>%s</default><defaultPull>0</defaultPull></value>"
            % (key, locked_default_current, escape(default)))


def _partial(ptype: str, conversion: str, value: str,
             scale_min: float = 0.0, scale_max: float = 1.0) -> str:
    """Build one <partial>, the building block of a path or an argument.

    ``scaleMin``/``scaleMax`` are what turn a control's native 0..1 travel into
    the number the receiver actually wants. An attractor knob is a -1..1
    OFFSET (``osc_profile_control.parse_osc_attractor_message``), so its fader
    sends -1..1 from the same 0..1 handle position, centre at rest.

    Args:
        ptype: CONSTANT, INDEX, VALUE or PROPERTY.
        conversion: BOOLEAN, INTEGER, FLOAT or STRING.
        value: Literal text for CONSTANT, else the value/property name.
        scale_min: Value sent at the low end of travel.
        scale_max: Value sent at the high end of travel.

    Returns:
        One <partial> element.
    """
    return ("<partial><type>%s</type><conversion>%s</conversion>"
            "<value>%s</value><scaleMin>%g</scaleMin><scaleMax>%g</scaleMax>"
            "</partial>" % (ptype, conversion, escape(value),
                            scale_min, scale_max))


def _address_partials(address: str) -> str:
    """Split an OSC address into the alternating partials the editor writes.

    ``/dj/profile/UV_RAVE`` becomes CONSTANT "/", CONSTANT "dj", CONSTANT "/",
    CONSTANT "profile", CONSTANT "/", CONSTANT "UV_RAVE" -- the exact shape a
    hand-built layout produces, so nothing depends on TouchOSC tolerating a
    single fused constant.

    Args:
        address: A leading-slash OSC address.

    Returns:
        The concatenated <partial> elements.
    """
    out = []
    for segment in address.strip("/").split("/"):
        out.append(_partial("CONSTANT", "STRING", "/"))
        out.append(_partial("CONSTANT", "STRING", segment))
    return "".join(out)


def _node(node_id: str, ntype: str, props: str, values: str,
          messages: str = "", children: str = "") -> str:
    """Assemble a <node> with its four sub-element blocks, in schema order.

    Args:
        node_id: UUID string.
        ntype: GROUP, BUTTON, LABEL, ...
        props: Concatenated <property> elements.
        values: Concatenated <value> elements.
        messages: Concatenated <osc>/<midi>/<local> elements.
        children: Concatenated child <node> elements; GROUP only.

    Returns:
        One <node> element.
    """
    body = ("<properties>%s</properties><values>%s</values>"
            "<messages>%s</messages>" % (props, values, messages))
    if children:
        body += "<children>%s</children>" % children
    return '<node ID="%s" type="%s">%s</node>' % (node_id, ntype, body)


# --- Controls ---------------------------------------------------------------

def _readable_text_colour(rgba: Sequence[float]) -> Tuple[float, float, float, float]:
    """Pick black or white caption text for a given button fill.

    White-on-lime is unreadable across a dark booth at arm's length; this keeps
    every caption legible without hand-tuning five colours.

    Args:
        rgba: The button fill.

    Returns:
        An RGBA text colour.
    """
    luma = 0.2126 * rgba[0] + 0.7152 * rgba[1] + 0.0722 * rgba[2]
    return _BLACK if luma > 0.55 else _WHITE


def _osc_message(address: str, scale_min: float = 0.0,
                 scale_max: float = 1.0) -> str:
    """Build the <osc> block that makes a control send something.

    Send-only in every case. Nothing on this page listens: TouchOSC receiving
    state would need the show to talk back, and a control surface that can be
    repositioned by the machine it is driving is a control surface Thomas
    cannot trust in the dark.

    Args:
        address: The full OSC address.
        scale_min: Value sent at the low end of the control's travel.
        scale_max: Value sent at the high end.

    Returns:
        One <osc> element.
    """
    return (
        "<osc><enabled>1</enabled><send>1</send><receive>0</receive>"
        "<feedback>0</feedback><connections>00001</connections>"
        "<triggers><trigger><var>x</var><condition>ANY</condition></trigger>"
        "</triggers>"
        "<path>%s</path>"
        "<arguments>%s</arguments></osc>"
        % (_address_partials(address),
           _partial("VALUE", "FLOAT", "x", scale_min, scale_max))
    )


def _button(name: str, x: int, y: int, w: int, h: int,
            address: Optional[str] = None,
            fill: Optional[Sequence[float]] = None,
            button_type: int = BUTTON_MOMENTARY,
            default: str = "0") -> str:
    """Build one button that sends its own OSC address.

    Momentary (``buttonType`` 0) with both press and release enabled: the tap
    sends 1, the lift sends 0, and the TD handler ignores the 0. See
    ``osc_profile_control.parse_osc_profile_message``. PANIC and the attractor
    reset want exactly that shape too -- one press, one packet.

    The audience enable switch is the exception and takes ``BUTTON_TOGGLE``,
    because ``audience_control.route`` reads its value rather than treating it
    as a press, so a momentary switch would turn the room on and immediately
    off again.

    Args:
        name: Node name. Defaults the address to this profile's address.
        x: Left edge within the root group.
        y: Top edge within the root group.
        w: Width in points.
        h: Height in points.
        address: Full OSC address. Defaults to ``<OSC_PREFIX>/<name>``.
        fill: RGBA fill. Defaults to the profile colour for ``name``.
        button_type: BUTTON_MOMENTARY or BUTTON_TOGGLE.
        default: Serialised default for the ``x`` value.

    Returns:
        One BUTTON <node>.
    """
    if address is None:
        address = "%s/%s" % (ctl.OSC_PREFIX, name)
    if fill is None:
        fill = COLOURS.get(name, _WHITE)
    props = "".join((
        _prop("b", "background", "1"),
        _prop("i", "buttonType", str(button_type)),
        _prop_colour("color", fill),
        _prop("f", "cornerRadius", "8"),
        _prop_frame(x, y, w, h),
        _prop("b", "grabFocus", "1"),
        _prop("b", "interactive", "1"),
        _prop("b", "locked", "0"),
        _prop("s", "name", name),
        _prop("i", "orientation", "0"),
        _prop("b", "outline", "1"),
        _prop("i", "outlineStyle", "0"),
        _prop("i", "pointerPriority", "0"),
        _prop("b", "press", "1"),
        _prop("b", "release", "1"),
        _prop("i", "shape", "1"),
        _prop("b", "valuePosition", "0"),
        _prop("b", "visible", "1"),
    ))
    values = _value("touch", "false") + _value("x", default)
    return _node(_nid("button:" + name), "BUTTON", props, values,
                 _osc_message(address))


def _fader(name: str, address: str, x: int, y: int, w: int, h: int,
           fill: Sequence[float], default: str,
           scale_min: float, scale_max: float) -> str:
    """Build one fader that sends a scaled continuous value.

    UNVERIFIED NODE TYPE. GROUP/BUTTON/LABEL were checked against an authentic
    editor-produced layout; no reference file available here contains a FADER,
    so the type name and the fader-specific properties below are reasoned from
    the shared schema rather than confirmed. The shared parts -- ``frame``,
    ``visible``, the <osc> block, the ``touch``/``x`` values -- are the same
    elements the buttons already prove, so the likely failure is cosmetic
    (wrong orientation, missing centre line) rather than an invisible control.
    ``main`` writes a fader-free fallback document for the case where it is not.

    Args:
        name: Node name.
        address: Full OSC address.
        x: Left edge within the root group.
        y: Top edge within the root group.
        w: Width in points.
        h: Height in points.
        fill: RGBA fill.
        default: Serialised resting handle position, 0..1.
        scale_min: Value sent at the bottom of travel.
        scale_max: Value sent at the top.

    Returns:
        One FADER <node>.
    """
    centred = "1" if scale_min < 0.0 else "0"
    props = "".join((
        _prop("b", "background", "1"),
        _prop("b", "bar", "1"),
        _prop("i", "barDisplay", "0"),
        _prop("b", "centered", centred),
        _prop_colour("color", fill),
        _prop("f", "cornerRadius", "8"),
        _prop("b", "cursor", "1"),
        _prop("i", "cursorDisplay", "0"),
        _prop_frame(x, y, w, h),
        _prop("b", "grabFocus", "1"),
        _prop("b", "grid", "0"),
        _prop("i", "gridSteps", "10"),
        _prop("b", "interactive", "1"),
        _prop("b", "locked", "0"),
        _prop("s", "name", name),
        # 0 is vertical: the frames below are tall, and a knob you ride with a
        # thumb wants the travel along the long axis.
        _prop("i", "orientation", "0"),
        _prop("b", "outline", "1"),
        _prop("i", "outlineStyle", "0"),
        _prop("i", "pointerPriority", "0"),
        # 0 is absolute: the handle goes where the thumb lands. Relative would
        # mean a knob that never resyncs after the show restarts.
        _prop("i", "response", "0"),
        _prop("i", "shape", "1"),
        _prop("b", "visible", "1"),
    ))
    values = _value("touch", "false") + _value("x", default)
    return _node(_nid("fader:" + name), "FADER", props, values,
                 _osc_message(address, scale_min, scale_max))


def _caption(name: str, text: str, x: int, y: int, w: int, h: int,
             size: int, colour: Sequence[float]) -> str:
    """Build a non-interactive label drawn over a button.

    TouchOSC buttons carry no text of their own, so every caption is a separate
    LABEL. ``interactive`` is off and ``background`` is off so the label is
    purely cosmetic and the tap falls through to the button beneath it.

    Args:
        name: Node name.
        text: The caption itself.
        x: Left edge within the root group.
        y: Top edge within the root group.
        w: Width in points.
        h: Height in points.
        size: Text size in points.
        colour: RGBA text colour.

    Returns:
        One LABEL <node>.
    """
    props = "".join((
        _prop("b", "background", "0"),
        _prop_colour("color", (0.0, 0.0, 0.0, 0.0)),
        _prop("f", "cornerRadius", "0"),
        _prop("i", "font", "0"),
        _prop_frame(x, y, w, h),
        _prop("b", "grabFocus", "0"),
        _prop("b", "interactive", "0"),
        _prop("b", "locked", "0"),
        _prop("s", "name", name),
        _prop("i", "orientation", "0"),
        _prop("b", "outline", "0"),
        _prop("i", "outlineStyle", "0"),
        _prop("i", "pointerPriority", "0"),
        _prop("i", "shape", "1"),
        _prop("i", "textAlignH", "2"),
        _prop("i", "textAlignV", "2"),
        _prop("b", "textClip", "1"),
        _prop_colour("textColor", colour),
        _prop("i", "textLength", "0"),
        _prop("i", "textSize", str(size)),
        _prop("b", "visible", "1"),
    ))
    # lockedDefaultCurrent=1 is how the editor stores a static caption.
    values = _value("text", text, "1") + _value("touch", "false")
    return _node(_nid("label:" + name), "LABEL", props, values)


# --- Live channel discovery -------------------------------------------------
# Everything below asks the owning module what exists. No list is kept here.

class Fader(NamedTuple):
    """One continuous control the strip must offer.

    Attributes:
        name: Node name.
        caption: What it reads on the pad.
        address: Full OSC address.
        fill: RGBA fill.
        default: Resting handle position, 0..1.
        scale_min: Value sent at the bottom of travel.
        scale_max: Value sent at the top.
    """

    name: str
    caption: str
    address: str
    fill: Tuple[float, float, float, float]
    default: str
    scale_min: float
    scale_max: float


class Action(NamedTuple):
    """One button the strip must offer, outside the profile grid.

    Attributes:
        name: Node name.
        caption: What it reads on the pad.
        address: Full OSC address.
        fill: RGBA fill.
        button_type: BUTTON_MOMENTARY or BUTTON_TOGGLE.
        default: Serialised default for the ``x`` value.
    """

    name: str
    caption: str
    address: str
    fill: Tuple[float, float, float, float]
    button_type: int
    default: str


def attractor_faders() -> List[Fader]:
    """Build one fader per live attractor knob.

    Read from ``osc_profile_control.attractor_addresses()``, which reads
    ``attractor_engine.DJ_CHANNELS``. Adding a knob there puts a fader here
    with no edit to this file -- that lockstep is the whole point.

    The reset address that function also returns is not a knob and becomes an
    action button instead, so it is filtered out by address rather than by
    re-deriving the channel list from a second source.

    Returns:
        One Fader per DJ channel, in engine order.
    """
    reset = "%s/reset" % ctl.ATTRACTOR_PREFIX
    out: List[Fader] = []
    for address in ctl.attractor_addresses():
        if address == reset:
            continue
        channel = address.rsplit("/", 1)[-1]
        # The value is a bounded -1..1 OFFSET, so the fader rests dead centre
        # and its zero point is a real position a thumb can find, not an end
        # stop. attractor_engine.DJ_SPAN decides what one unit is worth; this
        # side deliberately does not know or care.
        out.append(Fader(name="knob_%s" % channel, caption=channel.upper(),
                         address=address, fill=KNOB_COLOUR, default="0.5",
                         scale_min=-1.0, scale_max=1.0))
    return out


def _bare_controls() -> List[str]:
    """List the operator's bare audience controls, in the module's own order.

    A bare control is a single segment under ``AUDIENCE_PREFIX`` --
    ``/dj/audience/gain``. Anything with a further segment
    (``/dj/audience/nudge/GLOW``) is an audience verb and is filtered out; see
    the note on CONTROL_FADERS for why those do not belong on this pad.

    Raises:
        KeyError: If the module accepts a bare control this file has no
            presentation for. That is a capability with no button, which is the
            defect the whole generator exists to prevent, so it is raised
            loudly here rather than quietly dropped from the layout.

    Returns:
        Bare control names, e.g. ``["enable", "gain", "lock_profile"]``.
    """
    prefix = aud.AUDIENCE_PREFIX + "/"
    out: List[str] = []
    for address in aud.audience_addresses():
        if not address.startswith(prefix):
            continue
        rest = address[len(prefix):]
        if "/" in rest:
            continue
        if rest not in CONTROL_FADERS and rest not in CONTROL_TOGGLES:
            raise KeyError(
                "audience_control accepts %s but make_touchosc_layout has no "
                "presentation for it -- add it to CONTROL_FADERS or "
                "CONTROL_TOGGLES, or it reaches TouchDesigner with no button "
                "on the pad." % address)
        out.append(rest)
    return out


def audience_faders() -> List[Fader]:
    """Build a fader for each continuous audience control that exists.

    Presence is decided by ``audience_control.audience_addresses()`` rather
    than by assuming: a control is emitted only if that module still offers it.

    Returns:
        One Fader per live continuous control, in the module's order.
    """
    out: List[Fader] = []
    for control in _bare_controls():
        if control not in CONTROL_FADERS:
            continue
        caption, default, low, high = CONTROL_FADERS[control]
        out.append(Fader(name="aud_%s" % control, caption=caption,
                         address="%s/%s" % (aud.AUDIENCE_PREFIX, control),
                         fill=AUDIENCE_COLOUR, default=default,
                         scale_min=low, scale_max=high))
    return out


def actions() -> List[Action]:
    """Build the strip's buttons: reset, audience enable, panic.

    Ordered left to right by how much damage each does, PANIC last and alone
    on the right so the hand that reaches for it in the dark has an edge to
    aim at.

    Returns:
        The Actions whose addresses the owning modules still accept.
    """
    out = [Action(name="attractor_reset", caption="KNOBS 0",
                  address="%s/reset" % ctl.ATTRACTOR_PREFIX,
                  fill=RESET_COLOUR, button_type=BUTTON_MOMENTARY,
                  default="0")]

    # Toggles, in the order audience_control lists them, so the escalation on
    # the pad reads left to right the way it does in the head: hand off the
    # room (CROWD ON), take the look back (LOCK LOOK), stop everything (PANIC).
    for control in _bare_controls():
        if control not in CONTROL_TOGGLES:
            continue
        caption, default = CONTROL_TOGGLES[control]
        # Toggle, not momentary: `audience_control.route` reads these as a
        # VALUE, so a momentary switch would set the flag on the press and
        # clear it again on the lift.
        out.append(Action(name="audience_%s" % control, caption=caption,
                          address="%s/%s" % (aud.AUDIENCE_PREFIX, control),
                          fill=AUDIENCE_COLOUR, button_type=BUTTON_TOGGLE,
                          default=default))

    out.append(Action(name="panic", caption="PANIC",
                      address=aud.PANIC_ADDRESS, fill=PANIC_COLOUR,
                      button_type=BUTTON_MOMENTARY, default="0"))
    return out


def layout_addresses() -> List[str]:
    """List every OSC address this layout can send.

    The lockstep assertion lives against this: if a capability's address is
    reachable from the owning module and absent here, the iPad cannot reach it.

    Returns:
        Profile addresses, then knobs, then the strip's buttons.
    """
    return (ctl.osc_addresses()
            + [f.address for f in attractor_faders() + audience_faders()]
            + [a.address for a in actions()])


# --- Geometry ---------------------------------------------------------------

def _row_split(count: int, total_w: int, min_w: int,
               max_rows: int = 2) -> Tuple[int, int]:
    """Split ``count`` equal cells across as few rows as stay wide enough.

    The same rule `_grid` applies vertically: hold the minimum target size and
    take another row, rather than shrink below what a thumb can hit.

    Args:
        count: Number of cells.
        total_w: Width available to one row.
        min_w: Narrowest acceptable cell.
        max_rows: Cap on rows, so a runaway registry cannot eat the page.

    Returns:
        ``(rows, cell_width)``.
    """
    count = max(1, int(count))
    rows = 1
    while True:
        per_row = -(-count // rows)                     # ceil division
        cell_w = (total_w - STRIP_GAP * (per_row - 1)) // per_row
        if cell_w >= min_w or rows >= max_rows:
            return rows, cell_w
        rows += 1


def strip_height() -> int:
    """Height the live-control strip needs, given what is live right now.

    Computed rather than fixed, because the fader and action rows both wrap
    when their registries grow and a fixed band would silently clip whatever
    landed last -- the exact class of failure this whole change exists to end.

    Returns:
        Strip height in points.
    """
    total_w = WIDTH - 2 * MARGIN
    fader_rows, _ = _row_split(len(attractor_faders()) + len(audience_faders()),
                               total_w, MIN_FADER_W)
    action_rows, _ = _row_split(len(actions()), total_w, MIN_ACTION_W)
    # Rows are the caption, then the fader rows, then the action rows. Gaps sit
    # BETWEEN rows, so there is one fewer gap than rows -- no trailing gap, or
    # the strip reserves 12 pt it never draws in and PANIC stops at the wrong
    # place.
    height = (STRIP_LABEL_H
              + fader_rows * STRIP_FADER_H
              + action_rows * STRIP_ACTION_H
              + STRIP_GAP * (fader_rows + action_rows))
    return height


def _usable_height() -> int:
    """Height left for the profile grid once the title and strip are placed.

    Returns:
        Height in points.
    """
    return (HEIGHT - (2 * MARGIN) - LABEL_H - GAP - GAP - strip_height())


def _grid(count: int, usable_h: Optional[int] = None) -> Tuple[int, int, int]:
    """Solve the button grid for a given number of profiles.

    The thumb minimum is the fixed point. One column is preferred because it
    reads fastest, but once the registry grows past what a single column can
    give MIN_BUTTON_H to, the layout takes a second column rather than
    shrinking the targets -- a pad you cannot hit in the dark is worse than a
    pad you have to scan.

    Args:
        count: Number of buttons to place.
        usable_h: Height the grid may use. Defaults to whatever the title and
            the live-control strip leave behind.

    Returns:
        ``(columns, button_width, button_height)``.
    """
    count = max(1, int(count))
    if usable_h is None:
        usable_h = _usable_height()
    cols = 1
    while True:
        rows = -(-count // cols)                       # ceil division
        btn_h = (usable_h - GAP * (rows - 1)) // rows
        if btn_h >= MIN_BUTTON_H or cols >= MAX_COLUMNS:
            break
        cols += 1
    btn_w = (WIDTH - 2 * MARGIN - GAP * (cols - 1)) // cols
    return cols, btn_w, btn_h


def _build_strip() -> List[str]:
    """Build the live-control strip: knob faders, then the action buttons.

    Every control here comes from `attractor_faders`, `audience_faders` and
    `actions`, which read the owning modules. Nothing in this function knows
    the name of a knob.

    Returns:
        Child <node> elements, in draw order.
    """
    faders = attractor_faders() + audience_faders()
    buttons = actions()
    total_w = WIDTH - 2 * MARGIN
    fader_rows, fader_w = _row_split(len(faders), total_w, MIN_FADER_W)
    action_rows, action_w = _row_split(len(buttons), total_w, MIN_ACTION_W)
    per_fader_row = -(-len(faders) // fader_rows) if faders else 1
    per_action_row = -(-len(buttons) // action_rows) if buttons else 1

    y = HEIGHT - MARGIN - strip_height()
    children = [_caption("strip_title", "LIVE CONTROL", MARGIN, y,
                         total_w, STRIP_LABEL_H, 22, _WHITE)]
    y += STRIP_LABEL_H + STRIP_GAP

    for index, fader in enumerate(faders):
        col, row = index % per_fader_row, index // per_fader_row
        x = MARGIN + col * (fader_w + STRIP_GAP)
        fy = y + row * (STRIP_FADER_H + STRIP_GAP)
        children.append(_fader(fader.name, fader.address, x, fy,
                               fader_w, STRIP_FADER_H, fader.fill,
                               fader.default, fader.scale_min,
                               fader.scale_max))
        # The caption sits in the bottom sliver so it does not hide under the
        # handle at rest, and it is non-interactive so the drag falls through.
        children.append(_caption("%s_text" % fader.name, fader.caption,
                                 x, fy + STRIP_FADER_H - STRIP_LABEL_H,
                                 fader_w, STRIP_LABEL_H, 18,
                                 _readable_text_colour(fader.fill)))
    y += fader_rows * (STRIP_FADER_H + STRIP_GAP)

    for index, action in enumerate(buttons):
        col, row = index % per_action_row, index // per_action_row
        x = MARGIN + col * (action_w + STRIP_GAP)
        by = y + row * (STRIP_ACTION_H + STRIP_GAP)
        children.append(_button(action.name, x, by, action_w, STRIP_ACTION_H,
                                address=action.address, fill=action.fill,
                                button_type=action.button_type,
                                default=action.default))
        children.append(_caption("%s_text" % action.name, action.caption,
                                 x, by, action_w, STRIP_ACTION_H, 30,
                                 _readable_text_colour(action.fill)))
    return children


def build_xml(include_strip: bool = True) -> str:
    """Build the full layout document.

    Args:
        include_strip: False emits profile buttons only -- the document that
            shipped before the strip existed, kept as the fallback for a
            device that will not render a FADER. See `main`.

    Returns:
        The layout as an XML string.
    """
    names: List[str] = list(gp.PROFILES)
    usable_h = _usable_height() if include_strip else (
        HEIGHT - (2 * MARGIN) - LABEL_H - GAP)
    cols, btn_w, btn_h = _grid(len(names), usable_h)

    children: List[str] = [
        _caption("title", "DJ PROFILES", MARGIN, MARGIN,
                 WIDTH - 2 * MARGIN, LABEL_H, 40, _WHITE)
    ]
    top = MARGIN + LABEL_H + GAP
    for index, name in enumerate(names):
        fill = COLOURS.get(name, _WHITE)
        col, row = index % cols, index // cols
        x = MARGIN + col * (btn_w + GAP)
        y = top + row * (btn_h + GAP)
        # Button first, caption second: later siblings draw on top.
        children.append(_button(name, x, y, btn_w, btn_h))
        children.append(_caption("%s_text" % name, name.replace("_", " "),
                                 x, y, btn_w, btn_h, 34,
                                 _readable_text_colour(fill)))

    if include_strip:
        children.extend(_build_strip())

    root_props = "".join((
        _prop("b", "background", "1"),
        _prop_colour("color", (0.05, 0.05, 0.07, 1.0)),
        _prop("f", "cornerRadius", "0"),
        _prop_frame(0, 0, WIDTH, HEIGHT),
        _prop("b", "grabFocus", "0"),
        _prop("b", "interactive", "0"),
        _prop("b", "locked", "0"),
        _prop("s", "name", "DJ Profiles"),
        _prop("i", "orientation", "0"),
        _prop("b", "outline", "0"),
        _prop("i", "outlineStyle", "0"),
        _prop("i", "pointerPriority", "0"),
        _prop("i", "shape", "1"),
        _prop("b", "visible", "1"),
    ))
    root = _node(_nid("root"), "GROUP", root_props, _value("touch", "false"),
                 "", "".join(children))
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<lexml version="3">%s</lexml>' % root)


def main() -> int:
    """Write the .tosc plus two fallbacks.

    Returns:
        Process exit code.
    """
    xml = build_xml()
    written = []

    tosc_path = os.path.join(OUT_DIR, BASENAME + ".tosc")
    with open(tosc_path, "wb") as handle:
        # Level 6, not 9: TouchOSC's own files start 78 9c, and there is no
        # reason to hand a header the app has never seen to a loader we cannot
        # test against. Both are valid zlib; this one is what it expects.
        handle.write(zlib.compress(xml.encode("utf-8"), ZLIB_LEVEL))
    written.append((tosc_path, "TRY THIS FIRST -- zlib-compressed, the real format"))

    raw_path = os.path.join(OUT_DIR, BASENAME + "_uncompressed.tosc")
    with open(raw_path, "wb") as handle:
        handle.write(xml.encode("utf-8"))
    written.append((raw_path, "fallback -- same document, no zlib wrapper"))

    xml_path = os.path.join(OUT_DIR, BASENAME + ".xml")
    with open(xml_path, "w") as handle:
        handle.write(xml)
    written.append((xml_path, "readable reference / hand-inspection"))

    # The fallback. FADER is the one node type not checked against an authentic
    # editor file, and a layout that will not open is the failure this project
    # has already had once. Carrying a fader-free copy to the booth costs a few
    # kilobytes and removes that as a way to lose the night.
    fallback_path = os.path.join(OUT_DIR, BASENAME + FALLBACK_SUFFIX + ".tosc")
    with open(fallback_path, "wb") as handle:
        handle.write(zlib.compress(build_xml(include_strip=False).encode("utf-8"),
                                   ZLIB_LEVEL))
    written.append((fallback_path,
                    "FALLBACK -- profile buttons only, no FADER node"))

    for path, note in written:
        print("wrote %s  (%d bytes)  -- %s"
              % (path, os.path.getsize(path), note))

    print("\nOSC port %d, UDP. Set Host + Send Port on the device -- they are"
          % ctl.OSC_PORT)
    print("NOT stored in the layout file. Addresses:")
    for addr in layout_addresses():
        print("  " + addr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
