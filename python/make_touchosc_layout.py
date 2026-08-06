#!/usr/bin/env python3
"""Generate the TouchOSC layout for live graphics-profile switching.

FORMAT NOTE -- READ THIS
    A modern TouchOSC (Hexler, 2021+) ``.tosc`` file is a zlib-compressed XML
    document. This script writes that, and also writes the SAME document
    uncompressed as ``.xml`` beside it.

    I could not load-test the binary: that needs the TouchOSC app. If the
    ``.tosc`` does not open on the iPad, the ``.xml`` is there so nothing is
    lost, and docs/touchosc_profile_control.md has a 5-minute manual build that
    is guaranteed to work. Treat the .tosc as a convenience, not a certainty.

USAGE
    ./venv/bin/python python/make_touchosc_layout.py
"""

from __future__ import annotations

import os
import sys
import zlib
from typing import List
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

#: Button fill colours, chosen to echo each profile's own palette so the pad
#: reads at a glance in a dark booth. RGBA floats, TouchOSC's own format.
COLOURS = {
    "UV_RAVE": (1.0, 0.0, 1.0, 1.0),
    "DEEP_LASER": (0.1, 0.35, 1.0, 1.0),
    "STROBE_ACID": (0.35, 1.0, 0.06, 1.0),
    "VAPOR_UV": (1.0, 0.06, 0.55, 1.0),
    "MONO_PULSE": (0.0, 1.0, 1.0, 1.0),
}


def _prop(ptype: str, key: str, value: str) -> str:
    """Build one TouchOSC <property> element."""
    return ('<property type="%s"><key>%s</key><value>%s</value></property>'
            % (ptype, key, value))


def _frame(x: int, y: int, w: int, h: int) -> str:
    """Build the x/y/w/h properties shared by every node."""
    return "".join(_prop("i", k, str(v))
                   for k, v in (("x", x), ("y", y), ("w", w), ("h", h)))


def _colour(rgba) -> str:
    """Build a TouchOSC colour property."""
    r, g, b, a = rgba
    return ('<property type="c"><key>color</key><value>'
            '<r>%.3f</r><g>%.3f</g><b>%.3f</b><a>%.3f</a>'
            "</value></property>" % (r, g, b, a))


def _button(name: str, index: int, x: int, y: int, w: int, h: int) -> str:
    """Build one profile button that sends its own OSC address on press."""
    address = "%s/%s" % (ctl.OSC_PREFIX, name)
    props = (
        _prop("s", "name", escape(name))
        + _frame(x, y, w, h)
        + _colour(COLOURS.get(name, (1.0, 1.0, 1.0, 1.0)))
        + _prop("s", "text", escape(name.replace("_", " ")))
        + _prop("i", "textSize", "34")
        + _prop("b", "outline", "1")
    )
    # value 1 on press, 0 on release -- the handler ignores the release.
    message = (
        "<osc><enabled>1</enabled><send>1</send>"
        "<path>%s</path>"
        "<arguments><argument><type>f</type><value>1</value></argument></arguments>"
        "</osc>" % escape(address)
    )
    return ('<node ID="btn%d" type="BUTTON"><properties>%s</properties>'
            "<messages>%s</messages></node>" % (index, props, message))


def build_xml() -> str:
    """Build the full layout document.

    Returns:
        The layout as an XML string.
    """
    names: List[str] = list(gp.PROFILES)
    usable_h = HEIGHT - (2 * MARGIN) - LABEL_H - GAP
    btn_h = (usable_h - GAP * (len(names) - 1)) // len(names)
    btn_w = WIDTH - 2 * MARGIN

    children = [
        '<node ID="lbl" type="LABEL"><properties>'
        + _prop("s", "name", "current_profile")
        + _frame(MARGIN, MARGIN, btn_w, LABEL_H)
        + _prop("s", "text", "DJ PROFILES")
        + _prop("i", "textSize", "40")
        + "</properties><messages>"
        # Listens for TD's echo so the pad can show the live look.
        + ('<osc><enabled>1</enabled><receive>1</receive><path>%s/current</path></osc>'
           % escape(ctl.OSC_PREFIX))
        + "</messages></node>"
    ]
    y = MARGIN + LABEL_H + GAP
    for i, name in enumerate(names):
        children.append(_button(name, i, MARGIN, y, btn_w, btn_h))
        y += btn_h + GAP

    root_props = (_prop("s", "name", "DJ Profiles") + _frame(0, 0, WIDTH, HEIGHT))
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<lexml version="3">'
        '<node ID="root" type="GROUP"><properties>%s</properties>'
        "<children>%s</children></node></lexml>"
    ) % (root_props, "".join(children))


def main() -> int:
    """Write both the .tosc and the readable .xml.

    Returns:
        Process exit code.
    """
    xml = build_xml()
    xml_path = os.path.join(OUT_DIR, BASENAME + ".xml")
    tosc_path = os.path.join(OUT_DIR, BASENAME + ".tosc")

    with open(xml_path, "w") as handle:
        handle.write(xml)
    with open(tosc_path, "wb") as handle:
        handle.write(zlib.compress(xml.encode("utf-8"), 9))

    print("wrote %s  (%d bytes)" % (tosc_path, os.path.getsize(tosc_path)))
    print("wrote %s  (%d bytes, readable fallback)" % (xml_path, os.path.getsize(xml_path)))
    print("\nOSC port %d. Addresses:" % ctl.OSC_PORT)
    for addr in ctl.osc_addresses():
        print("  " + addr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
