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

USAGE
    ./venv/bin/python python/make_touchosc_layout.py
"""

from __future__ import annotations

import os
import sys
import uuid
import zlib
from typing import Dict, List, Sequence, Tuple
from xml.sax.saxutils import escape

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "touchdesigner", "scripts"))

import dj_graphics_profiles as gp  # noqa: E402
import osc_profile_control as ctl  # noqa: E402

#: AirDrop target. ~/Desktop so it is trivial to find and send to both devices.
OUT_DIR = os.path.expanduser("~/Desktop")
BASENAME = "DJ_Profiles"

#: Layout geometry, sized for an iPhone screen so it also works on an iPad.
WIDTH, HEIGHT = 720, 1280
MARGIN, GAP = 40, 24
LABEL_H = 90

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
}

_WHITE = (1.0, 1.0, 1.0, 1.0)
_BLACK = (0.0, 0.0, 0.0, 1.0)


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


def _partial(ptype: str, conversion: str, value: str) -> str:
    """Build one <partial>, the building block of a path or an argument.

    Args:
        ptype: CONSTANT, INDEX, VALUE or PROPERTY.
        conversion: BOOLEAN, INTEGER, FLOAT or STRING.
        value: Literal text for CONSTANT, else the value/property name.

    Returns:
        One <partial> element.
    """
    return ("<partial><type>%s</type><conversion>%s</conversion>"
            "<value>%s</value><scaleMin>0</scaleMin><scaleMax>1</scaleMax>"
            "</partial>" % (ptype, conversion, escape(value)))


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


def _button(name: str, x: int, y: int, w: int, h: int) -> str:
    """Build one profile button that sends its own OSC address.

    Momentary (``buttonType`` 0) with both press and release enabled: the tap
    sends 1, the lift sends 0, and the TD handler ignores the 0. See
    ``osc_profile_control.parse_osc_profile_message``.

    Args:
        name: Profile name, e.g. ``UV_RAVE``.
        x: Left edge within the root group.
        y: Top edge within the root group.
        w: Width in points.
        h: Height in points.

    Returns:
        One BUTTON <node>.
    """
    fill = COLOURS.get(name, _WHITE)
    props = "".join((
        _prop("b", "background", "1"),
        _prop("i", "buttonType", "0"),
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
    values = _value("touch", "false") + _value("x", "0")
    message = (
        "<osc><enabled>1</enabled><send>1</send><receive>0</receive>"
        "<feedback>0</feedback><connections>00001</connections>"
        "<triggers><trigger><var>x</var><condition>ANY</condition></trigger>"
        "</triggers>"
        "<path>%s</path>"
        "<arguments>%s</arguments></osc>"
        % (_address_partials("%s/%s" % (ctl.OSC_PREFIX, name)),
           _partial("VALUE", "FLOAT", "x"))
    )
    return _node(_nid("button:" + name), "BUTTON", props, values, message)


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


def build_xml() -> str:
    """Build the full layout document.

    Returns:
        The layout as an XML string.
    """
    names: List[str] = list(gp.PROFILES)
    usable_h = HEIGHT - (2 * MARGIN) - LABEL_H - GAP
    btn_h = (usable_h - GAP * (len(names) - 1)) // len(names)
    btn_w = WIDTH - 2 * MARGIN

    children: List[str] = [
        _caption("title", "DJ PROFILES", MARGIN, MARGIN, btn_w, LABEL_H,
                 40, _WHITE)
    ]
    y = MARGIN + LABEL_H + GAP
    for name in names:
        fill = COLOURS.get(name, _WHITE)
        # Button first, caption second: later siblings draw on top.
        children.append(_button(name, MARGIN, y, btn_w, btn_h))
        children.append(_caption("%s_text" % name, name.replace("_", " "),
                                 MARGIN, y, btn_w, btn_h, 34,
                                 _readable_text_colour(fill)))
        y += btn_h + GAP

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

    for path, note in written:
        print("wrote %s  (%d bytes)  -- %s"
              % (path, os.path.getsize(path), note))

    print("\nOSC port %d, UDP. Set Host + Send Port on the device -- they are"
          % ctl.OSC_PORT)
    print("NOT stored in the layout file. Addresses:")
    for addr in ctl.osc_addresses():
        print("  " + addr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
