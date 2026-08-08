# attractor_pipeline.py -- builds the attractor render chain inside TouchDesigner
# =============================================================================
# WHAT THIS IS
#   The node builder for the chaotic-attractor engine. Paste into the Textport
#   (Alt+T). Idempotent -- re-pasting reuses every node and only re-asserts
#   wiring, exactly like extend_dj_graphics.py.
#
#       install_attractor()        # build the engine and splice it in
#       attractor_teardown()       # remove it; the chain returns to normal
#       attractor_status()         # what exists, what is bound, what is cooking
#       set_dj('chaos', 0.4)       # Thomas's live offsets (also over OSC)
#       zero_dj()                  # back to the profile's own values
#
# WHERE IT SPLICES IN -- the one structural change, stated plainly
#   The existing chain is
#       final_composite -> fx_palette_apply -> fx_trail_comp -> fx_kick_comp
#                       -> fx_snare_shake -> fx_out -> syphonOut1
#
#   This inserts ONE composite between the palette and the trails:
#       fx_palette_apply --\
#                           attr_comp (add) -> fx_trail_comp / fx_trail_feedback
#       attr_level --------/
#
#   That position is the whole integration argument. Upstream of the trails
#   means the attractor inherits, with no new code and no new caps:
#     * the feedback trails and their TRAIL_VALUEMULT_HARD_CAP,
#     * the kick flash and its KICK_FLASH_HARD_CAP (and with it the
#       photosensitivity ceiling that already lives in that expression),
#     * the snare shake, the radial zoom, the outline glow,
#     * and every audience nudge that already rides those nodes.
#   Downstream of the palette means it is coloured by the same sweep the
#   silhouette is, so the two layers can never disagree about the look.
#
#   Only two connections change (`fx_trail_comp` input 0 and
#   `fx_trail_feedback` input 0), and `attractor_teardown()` puts both back.
#
# THE FEEDBACK TOP GOTCHA, AGAIN
#   "Not enough sources specified" comes from the COMPOSITE, not the Feedback
#   TOP, and it fires the instant a Composite cooks with fewer than two
#   connected inputs. attr_comp is therefore wired input 0 THEN input 1 before
#   anything downstream is touched. Same lesson as extend_dj_graphics.py.
#
# FREEZE SAFETY
#   One Script CHOP with an onCook callback. No audio tap, no CHOP Execute DAT,
#   no per-FFT-bin anything. The per-cook cost is bounded at construction by
#   attractor_engine.ATTRACTOR_MAX_POINTS.
#
# OBS
#   Nothing here talks to OBS. Syphon stays overlay-only.
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, List, Optional

import attractor_engine as ae

PARENT = "/project1"

#: The node this engine composites ON TOP OF, and the two nodes whose input 0
#: gets repointed at the result. All three are built by extend_dj_graphics.py.
UPSTREAM = "fx_palette_apply"
DOWNSTREAM = ("fx_trail_comp", "fx_trail_feedback")

#: Every node this file creates. Named in one place so teardown cannot drift
#: from build -- the most common way an "idempotent" installer stops being one.
NODES = ("attr_dj", "attr_ctl", "attr_engine_cb", "attr_engine", "attr_geo",
         "attr_cam", "attr_render", "attr_level", "attr_out", "attr_comp",
         "attr_mat")

OUT_W, OUT_H = 1280, 720
#: Camera distance. The normalised attractor lives inside ~1.5 units and
#: `spread` scales it; at the default 45-degree field of view this frames the
#: whole form with margin for a full-chaos excursion.
CAM_Z = 3.5


def _log(msg: str) -> None:
    """Print a namespaced line to the Textport.

    Args:
        msg: The message body.
    """
    print("[attractor] " + msg)


def _in_td() -> bool:
    """Report whether TD globals are present.

    Returns:
        True inside TouchDesigner, False under pytest.
    """
    try:
        op  # noqa: B018, F821 - TD injects this
        return True
    except NameError:
        return False


def _parent() -> Optional[Any]:
    """Resolve the COMP the DJ_Graphics chain lives in.

    Returns:
        The COMP, or None.
    """
    try:
        return op(PARENT)  # noqa: F821
    except Exception:
        return None


def _resolve(name: str) -> Optional[Any]:
    """Look up a node under PARENT, returning None instead of raising.

    Args:
        name: Node name relative to PARENT.

    Returns:
        The operator, or None.
    """
    parent = _parent()
    if parent is None:
        return None
    try:
        return parent.op(name)
    except Exception:
        return None


def _make(kind: Any, name: str, x: int, y: int,
          parent: Optional[Any] = None) -> Optional[Any]:
    """Create or reuse a node and place it on the layout grid.

    Args:
        kind: TD operator type.
        name: Node name.
        x: nodeX.
        y: nodeY.
        parent: COMP to create inside; defaults to PARENT.

    Returns:
        The operator, or None if the parent is missing.
    """
    host = parent if parent is not None else _parent()
    if host is None:
        return None
    node = host.op(name)
    if node is None:
        node = host.create(kind, name)
        _log("create %s (%s)" % (name, node.type))
    else:
        _log("reuse  %s (%s)" % (name, node.type))
    node.nodeX, node.nodeY = x, y
    return node


def _par(node: Any, names: List[str], value: Any) -> bool:
    """Set the first parameter in ``names`` that exists on this build.

    Parameter names drift between TD builds, so every write tries candidates
    rather than assuming one spelling. Same discipline as
    `dj_graphics_profiles._set_val`.

    Args:
        node: Target operator.
        names: Candidate parameter names, most likely first.
        value: Value to write.

    Returns:
        True if a parameter was written.
    """
    if node is None:
        return False
    for name in names:
        if hasattr(node.par, name):
            try:
                setattr(getattr(node.par, name), "val", value)
                return True
            except Exception as exc:
                _log("  par %s.%s: %s" % (node.name, name, exc))
                return False
    _log("  none of %s on %s" % (names, node.name))
    return False


def _expr(node: Any, names: List[str], expression: str) -> bool:
    """Bind the first parameter in ``names`` that exists on this build.

    Args:
        node: Target operator.
        names: Candidate parameter names, most likely first.
        expression: Expression to bind.

    Returns:
        True if a parameter was bound.
    """
    if node is None:
        return False
    for name in names:
        if hasattr(node.par, name):
            try:
                getattr(node.par, name).expr = expression
                return True
            except Exception as exc:
                _log("  expr %s.%s: %s" % (node.name, name, exc))
                return False
    _log("  none of %s on %s (expr)" % (names, node.name))
    return False


def _wire(src: Any, dst: Any, index: int = 0) -> bool:
    """Connect ``src`` into ``dst`` input ``index``.

    Args:
        src: Source operator.
        dst: Destination operator.
        index: Input connector index.

    Returns:
        True if connected.
    """
    if src is None or dst is None:
        _log("  wire skip (missing op): %s -> %s" % (src, dst))
        return False
    try:
        dst.inputConnectors[index].connect(src)
        return True
    except Exception as exc:
        _log("  wire %s -> %s[%d]: %s" % (src.name, dst.name, index, exc))
        return False


def _ctl(channel: str) -> str:
    """Build an expression reading one attr_ctl channel.

    Args:
        channel: A member of ``attractor_engine.CTL_CHANNELS``.

    Returns:
        A TD expression fragment.

    Raises:
        KeyError: On an unknown channel.
    """
    if channel not in ae.CTL_CHANNELS:
        raise KeyError("no such attr_ctl channel: %r" % channel)
    return "op('%s')['%s']" % (ae.CTL_CHOP, channel)


# =============================================================================
# BUILD
# =============================================================================


def _build_controls() -> Dict[str, Any]:
    """Create the two Constant CHOPs that carry every knob.

    `attr_dj` holds Thomas's live offsets as plain values. `attr_ctl` holds the
    resolved knobs; `apply_profile()` binds EXPRESSIONS to its value parameters
    so the audio terms, the DJ offsets and (when installed) the audience terms
    all sum inside the same clamps.

    Returns:
        ``{"dj": chop, "ctl": chop}``.
    """
    dj = _make(constantCHOP, "attr_dj", 250, -1150)  # noqa: F821
    if dj is not None:
        try:
            dj.par.name0.sequence.numBlocks = len(ae.DJ_CHANNELS)
        except Exception:
            pass
        for i, name in enumerate(ae.DJ_CHANNELS):
            _par(dj, ["name%d" % i], name)
            _par(dj, ["value%d" % i], 0.0)

    ctl = _make(constantCHOP, "attr_ctl", 500, -1150)  # noqa: F821
    if ctl is not None:
        try:
            ctl.par.name0.sequence.numBlocks = len(ae.CTL_CHANNELS)
        except Exception:
            pass
        for i, name in enumerate(ae.CTL_CHANNELS):
            _par(ctl, ["name%d" % i], name)
            # Default DARK. install_attractor() does not turn the engine on --
            # applying an attractor PROFILE does. Building the nodes and
            # choosing the look stay two separate decisions, the same way
            # installing fx_audience and enabling the audience do.
            _par(ctl, ["value%d" % i], 0.0)
    return {"dj": dj, "ctl": ctl}


def _build_engine() -> Optional[Any]:
    """Create the Script CHOP that integrates the attractor.

    Returns:
        The Script CHOP, or None.
    """
    cb = _make(textDAT, "attr_engine_cb", 250, -1300)  # noqa: F821
    if cb is not None:
        cb.text = ae.ENGINE_CALLBACK_CODE
    engine = _make(scriptCHOP, "attr_engine", 500, -1300)  # noqa: F821
    if engine is not None and cb is not None:
        _par(engine, ["callbacks"], cb)
    return engine


def _build_render(engine: Any) -> Optional[Any]:
    """Create the geometry, material, camera and Render TOP.

    The point cloud is drawn as INSTANCED sprites straight off the Script CHOP
    -- no SOP conversion, no CHOP-to-TOP round trip. At the 16 k ceiling this
    engine enforces, direct CHOP instancing is both simpler and faster; the
    CHOP-to-TOP path the aura pipeline uses only pays for itself past ~100 k
    instances, and getting there means the GLSL engine, not this one.

    Args:
        engine: The Script CHOP holding tx/ty/tz/fade.

    Returns:
        The Render TOP, or None.
    """
    mat = _make(constantMAT, "attr_mat", 750, -1300)  # noqa: F821
    if mat is not None:
        # Additive, depth-test off: this is glowing light, not lit surfaces, so
        # overlapping particles should build up rather than occlude.
        _par(mat, ["blending"], True)
        _par(mat, ["srcblend", "sourceblend"], "one")
        _par(mat, ["destblend", "destinationblend"], "one")
        _par(mat, ["depthtest"], False)
        _par(mat, ["alpha"], 1.0)
        # Colour is bound per-profile by apply_profile(); a neutral default
        # keeps the node legible if it is ever cooked before a profile lands.
        for par_name in ("colorr", "colorg", "colorb"):
            _par(mat, [par_name], 1.0)

    geo = _make(geometryCOMP, "attr_geo", 750, -1150)  # noqa: F821
    if geo is not None:
        sprite = geo.op("attr_sprite") or geo.create(circleSOP, "attr_sprite")  # noqa: F821
        _par(sprite, ["type"], "poly")
        _par(sprite, ["arc"], "closed")
        # Six sides is plenty for a sub-pixel-to-few-pixel sprite and costs a
        # third of the triangles of the default.
        _par(sprite, ["divisions"], 6)
        for par_name in ("radiusx", "radius1", "radx"):
            if hasattr(sprite.par, par_name):
                _expr(sprite, [par_name], _ctl("size"))
                break
        for par_name in ("radiusy", "radius2", "rady"):
            if hasattr(sprite.par, par_name):
                _expr(sprite, [par_name], _ctl("size"))
                break
        _par(sprite, ["render", "display"], True)
        _par(geo, ["material"], mat)
        _par(geo, ["instancing", "instance"], True)
        _par(geo, ["instanceop", "instanceop0"], engine)
        _par(geo, ["instancetx", "instancetx0"], "tx")
        _par(geo, ["instancety", "instancety0"], "ty")
        _par(geo, ["instancetz", "instancetz0"], "tz")
        # Per-instance scale from the fade channel: the oldest point of a trail
        # shrinks to nothing. Additive blending turns that into a fade without
        # needing per-instance alpha.
        for axis in ("x", "y", "z"):
            _par(geo, ["instances%s" % axis, "instancescale%s" % axis], "fade")
        # The whole cloud scaled by `spread`, and turned slowly by `spin` so the
        # 3D structure reads as 3D on a 2D stream.
        for axis in ("sx", "sy", "sz"):
            _expr(geo, [axis, "scale%s" % axis[1]], _ctl("spread"))
        _expr(geo, ["ry", "rotatey"], _ctl("spin"))

    cam = _make(cameraCOMP, "attr_cam", 750, -1000)  # noqa: F821
    if cam is not None:
        _par(cam, ["tz", "translatez"], CAM_Z)
        _par(cam, ["tx", "translatex"], 0.0)
        _par(cam, ["ty", "translatey"], 0.0)

    render = _make(renderTOP, "attr_render", 1000, -1150)  # noqa: F821
    if render is not None:
        _par(render, ["camera"], cam)
        _par(render, ["geometry"], geo)
        _par(render, ["outputresolution"], "custom")
        _par(render, ["resolutionw"], OUT_W)
        _par(render, ["resolutionh"], OUT_H)
        _par(render, ["bgalpha"], 0.0)
    return render


def _build_output(render: Any) -> Optional[Any]:
    """Create the enable gate and the null the composite reads.

    Returns:
        The output Null TOP, or None.

    Args:
        render: The Render TOP.
    """
    level = _make(levelTOP, "attr_level", 1250, -1150)  # noqa: F821
    _wire(render, level, 0)
    if level is not None:
        # THE OFF SWITCH. Every non-attractor profile writes enable = 0, so
        # tapping UV_RAVE makes the engine invisible in the same frame -- and
        # `cook()` short-circuits on the same channel, so it also stops costing
        # anything. One channel, both effects.
        _expr(level, ["opacity"], _ctl("enable"))
    out = _make(nullTOP, "attr_out", 1500, -1150)  # noqa: F821
    _wire(level, out, 0)
    return out


def _splice(out: Any) -> List[str]:
    """Insert the attractor composite between the palette and the trails.

    Returns:
        Human-readable outcome lines.

    Args:
        out: The attractor's output Null TOP.
    """
    report: List[str] = []
    upstream = _resolve(UPSTREAM)
    if upstream is None:
        report.append("WARN %s absent -- run extend_dj_graphics.py first; "
                      "nothing was spliced" % UPSTREAM)
        return report

    comp = _make(compositeTOP, "attr_comp", 1750, -1150)  # noqa: F821
    if comp is None:
        report.append("ERR  could not create attr_comp")
        return report
    _par(comp, ["operand"], "add")
    _par(comp, ["outputresolution"], "custom")
    _par(comp, ["resolutionw"], OUT_W)
    _par(comp, ["resolutionh"], OUT_H)
    # BOTH inputs before anything downstream cooks -- see the gotcha note.
    _wire(upstream, comp, 0)
    _wire(out, comp, 1)
    report.append("OK   attr_comp = add(%s, attr_out)" % UPSTREAM)

    for name in DOWNSTREAM:
        node = _resolve(name)
        if node is None:
            report.append("WARN %s absent -- not repointed" % name)
            continue
        if _wire(comp, node, 0):
            report.append("OK   %s input 0 <- attr_comp" % name)
        else:
            report.append("ERR  could not repoint %s" % name)
    return report


def install_attractor() -> Dict[str, Any]:
    """Build the attractor engine and splice it into the FX chain. Idempotent.

    Building the nodes does NOT turn the attractor on: `attr_ctl.enable`
    defaults to 0 and only an attractor PROFILE sets it. Install, then tap a
    look -- the same two-step the audience layer uses, and for the same reason:
    the moment a thing becomes visible should be a decision, not a side effect.

    Returns:
        A result dict with ``installed`` (bool) and ``report`` (list of lines).
    """
    result: Dict[str, Any] = {"installed": False, "report": []}
    report: List[str] = result["report"]

    if not _in_td():
        _log("not inside TouchDesigner -- nothing installed")
        report.append("ERR  no TD context")
        return result
    if _parent() is None:
        _log("%s not found" % PARENT)
        report.append("ERR  %s not found" % PARENT)
        return result

    _log("=== installing the chaotic-attractor engine ===")
    _build_controls()
    engine = _build_engine()
    render = _build_render(engine)
    out = _build_output(render)
    report += _splice(out)

    result["installed"] = True
    for line in report:
        _log("  " + line)
    _log("nodes built and dark. Now tap a look:")
    _log("    import dj_graphics_profiles as gp; gp.apply_profile('ATTRACTOR')")
    _log("or over OSC:  /dj/profile/ATTRACTOR")
    _log("live tweaks:  /dj/attractor/<%s>  -1..1" % "|".join(ae.DJ_CHANNELS))
    _log("remove:       attractor_teardown()")
    return result


def attractor_teardown() -> Dict[str, Any]:
    """Remove every attractor node and restore the original chain wiring.

    Returns:
        A result dict with ``report``.
    """
    result: Dict[str, Any] = {"report": []}
    report: List[str] = result["report"]
    if not _in_td():
        return result

    upstream = _resolve(UPSTREAM)
    for name in DOWNSTREAM:
        node = _resolve(name)
        if node is not None and upstream is not None:
            if _wire(upstream, node, 0):
                report.append("OK   %s input 0 <- %s (restored)" % (name, UPSTREAM))

    for name in NODES:
        node = _resolve(name)
        if node is not None:
            node.destroy()
            report.append("OK   removed %s" % name)

    ae.reset_engine()
    for line in report:
        _log("  " + line)
    _log("teardown complete -- the chain is back to %s -> %s"
         % (UPSTREAM, DOWNSTREAM[0]))
    return result


# =============================================================================
# THE DJ's LIVE OFFSETS
#
# Written by `/dj/attractor/<channel>` (see osc_profile_control.py) or by hand
# from the Textport. They are summed INSIDE the same clamps the audience terms
# are summed inside -- one control surface, one set of caps, a wider span for
# the person in the room.
# =============================================================================


def set_dj(channel: str, value: float) -> bool:
    """Write one attr_dj offset.

    Args:
        channel: A member of ``attractor_engine.DJ_CHANNELS``.
        value: Offset in -1..1. Clamped here as well as in the expression --
            this parameter is reachable by any UDP packet on the LAN, and a
            clamp at every hop is the same discipline the audience path uses.

    Returns:
        True if written.
    """
    if channel not in ae.DJ_CHANNELS:
        _log("no such attr_dj channel: %r" % channel)
        return False
    node = _resolve(ae.DJ_CHOP)
    if node is None:
        return False
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return False
    if amount != amount or amount in (float("inf"), float("-inf")):
        return False
    amount = max(-1.0, min(1.0, amount))
    index = ae.DJ_CHANNELS.index(channel)
    try:
        setattr(getattr(node.par, "value%d" % index), "val", amount)
        return True
    except Exception as exc:
        _log("could not write %s: %s" % (channel, exc))
        return False


def zero_dj() -> None:
    """Return every DJ offset to zero, i.e. to the profile's own values."""
    for channel in ae.DJ_CHANNELS:
        set_dj(channel, 0.0)


def attractor_status() -> Dict[str, Any]:
    """Report what exists, what is bound and what the engine last did.

    Returns:
        A dict of node name -> present/absent, plus the engine's diagnostics.
        The escape count is the one to watch: nonzero cook after cook means a
        parameter window is wrong, and nothing else will say so.
    """
    status: Dict[str, Any] = {"nodes": {}, "stats": ae.attractor_stats()}
    for name in NODES:
        status["nodes"][name] = _resolve(name) is not None
    ctl = _resolve(ae.CTL_CHOP)
    status["enabled"] = bool(ae._read(ctl, "enable", 0.0) > 0.0)
    for line in ("%-16s %s" % (k, "present" if v else "ABSENT")
                 for k, v in status["nodes"].items()):
        _log(line)
    _log("enabled: %s" % status["enabled"])
    _log("last cook: %s" % status["stats"])
    return status


if _in_td():  # pragma: no cover - only inside TouchDesigner
    install_attractor()
