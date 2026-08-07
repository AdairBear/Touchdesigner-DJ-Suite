# osc_profile_control.py -- LIVE profile switching from TouchOSC (iPad/iPhone)
# =============================================================================
# WHAT THIS IS
#   An OSC In DAT + handler that calls dj_graphics_profiles.apply_profile() when
#   a TouchOSC button fires. The look changes INSIDE the running show network --
#   no reload, no dropped frames, usable mid-set.
#
#   Paste into the TD Textport (Alt+T). Idempotent: re-pasting reuses the nodes.
#       install_osc_profile_control()     # build + wire it
#       osc_profile_teardown()            # remove it
#
# WHY NOT OPEN A DIFFERENT .toe
#   The per-profile .toe files (touchdesigner/profiles/) are the PRE-SHOW
#   option: opening one reloads TouchDesigner, which is unusable mid-set. This
#   path is the LIVE option. Same five profiles, same apply_profile(), two
#   different moments in the night.
#
# OSC CONTRACT
#   Port 7400 (UDP). Two accepted forms, so either TouchOSC button style works:
#       /dj/profile/STROBE_ACID   <any>     -- address carries the name
#       /dj/profile               "STROBE_ACID" | <int index>
#   A button that sends 1 on press and 0 on release fires ONCE: a zero/false
#   argument is treated as a release and ignored, so a look does not re-apply
#   when your finger lifts.
#
#   Anything on this port that is NOT /dj/profile/* is offered to
#   audience_control.py, which owns the /dj/audience/* namespace and /dj/panic.
#   The split is deliberate and load-bearing: the audience kill switch gates
#   only the audience namespace, so turning the room off never turns Thomas
#   off. A tap here also arms a 60 s audience lockout, so his choice is not
#   overwritten by a vote that was already in flight.
#
# FREEZE SAFETY (unchanged from the profile system)
#   This adds NO audio tap and NO CHOP Execute DAT. It is a DAT Execute on an
#   OSC In DAT, which fires only when a UDP packet arrives -- a few times a
#   night, not once per FFT bin per frame. apply_profile() itself only rewrites
#   a table and re-binds parameter expressions. The freeze cannot come from here.
#
# OBS
#   Nothing in this file talks to OBS. The "Radio DJ" scene is untouched.
# =============================================================================

from __future__ import annotations

from typing import Any, List, Optional

#: UDP port the OSC In DAT listens on. 7000 is already taken by the tracker's
#: body-data stream, so this is deliberately distinct.
OSC_PORT = 7400

#: Address prefix for a per-profile button.
OSC_PREFIX = "/dj/profile"

PARENT = "/project1"
DAT_NAME = "osc_profile_in"
HANDLER_NAME = "osc_profile_handler"


def _profiles() -> Any:
    """Import the profile registry, working both in TD and under pytest.

    Returns:
        The dj_graphics_profiles module.
    """
    import dj_graphics_profiles as gp

    return gp


def parse_osc_profile_message(address: str, args: Optional[List[Any]] = None
                              ) -> Optional[str]:
    """Resolve an OSC message to a profile name, or None to ignore it.

    Pure and TD-free so the whole contract is unit-testable: what a tap does is
    decided here, not inside a callback that needs a running show to exercise.

    Ignoring is the default. An unrecognised address, an unknown profile, or a
    button RELEASE (a zero/false argument) all return None rather than guessing
    -- a stray packet must never change the look mid-set.

    Args:
        address: The OSC address, e.g. ``/dj/profile/STROBE_ACID``.
        args: OSC arguments. A single falsy numeric arg means "released".

    Returns:
        A profile name present in the registry, or None.
    """
    if not address:
        return None
    gp = _profiles()
    address = address.rstrip("/")

    # A button that sends 1 on press and 0 on release must fire once, on press.
    if args:
        first = args[0]
        if isinstance(first, bool) and not first:
            return None
        if isinstance(first, (int, float)) and float(first) == 0.0:
            return None

    if address.startswith(OSC_PREFIX + "/"):
        name = address[len(OSC_PREFIX) + 1:]
        return name if name in gp.PROFILES else None

    if address == OSC_PREFIX and args:
        first = args[0]
        if isinstance(first, str):
            return first if first in gp.PROFILES else None
        if isinstance(first, bool):
            return None
        if isinstance(first, (int, float)):
            # 1-based index, matching how a TouchOSC radio/selector counts.
            names = list(gp.PROFILES)
            idx = int(first) - 1
            return names[idx] if 0 <= idx < len(names) else None
    return None


def osc_addresses() -> List[str]:
    """List the per-profile OSC addresses, for the layout and the docs.

    Returns:
        One address per registered profile, in registry order.
    """
    return ["%s/%s" % (OSC_PREFIX, name) for name in _profiles().PROFILES]


# --- Handler installed into TD ----------------------------------------------
# Kept as source text so the DAT is rebuilt from this file rather than hand-
# edited in the .toe -- the same lesson that produced td_startup_hooks.py.
HANDLER_CODE = '''# osc_profile_handler -- generated by osc_profile_control.py
# Fires only when an OSC packet arrives. No audio tap, no per-frame work.
import sys
SCRIPTS = "/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts"
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


def onTableChange(dat):
    """OSC In DAT appends a row per message: [address, arg0, arg1, ...]."""
    if dat.numRows == 0:
        return
    try:
        import osc_profile_control as ctl
        import dj_graphics_profiles as gp
    except Exception as e:
        print("[osc_profile] import failed:", e)
        return
    row = dat.rows()[-1]
    address = str(row[0].val)
    args = []
    for cell in row[1:]:
        raw = str(cell.val)
        try:
            args.append(float(raw))
        except ValueError:
            args.append(raw)
    name = ctl.parse_osc_profile_message(address, args)
    if name is None:
        # Not one of Thomas's buttons. It may be audience traffic, which is a
        # different namespace and a different set of gates -- see
        # audience_control.py. If that module is not installed, nothing here
        # changes and audience packets are simply ignored.
        try:
            import audience_control as aud
        except Exception:
            return
        aud.handle(address, args)
        return
    print("[osc_profile] ->", name)
    gp.apply_profile(name)
    # His action wins, and keeps winning: arm the audience lockout so a vote
    # already in flight cannot flip the look back eight seconds later.
    try:
        import audience_control as aud
        import time as _time
        aud.STATE.arm_lockout(_time.monotonic())
        aud.STATE.current_profile = name
    except Exception:
        pass
    label = op("osc_profile_current")
    if label is not None:
        try:
            label.par.text = name
        except Exception:
            pass
    return
'''


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


def install_osc_profile_control() -> Optional[Any]:
    """Create and wire the OSC In DAT + handler. Idempotent.

    Returns:
        The OSC In DAT, or None if not running inside TouchDesigner.
    """
    if not _in_td():
        print("[osc_profile] not inside TouchDesigner -- nothing installed")
        return None
    parent = op(PARENT)  # noqa: F821
    if parent is None:
        print("[osc_profile] %s not found" % PARENT)
        return None

    handler = parent.op(HANDLER_NAME) or parent.create(textDAT, HANDLER_NAME)  # noqa: F821
    handler.text = HANDLER_CODE
    handler.nodeX, handler.nodeY = 0, -900

    osc = parent.op(DAT_NAME) or parent.create(oscinDAT, DAT_NAME)  # noqa: F821
    osc.nodeX, osc.nodeY = 250, -900
    for par_name, value in (("port", OSC_PORT), ("callbacks", handler),
                            ("active", True)):
        if hasattr(osc.par, par_name):
            try:
                setattr(getattr(osc.par, par_name), "val", value)
            except Exception as exc:
                print("[osc_profile] par %s: %s" % (par_name, exc))

    print("[osc_profile] listening on UDP %d" % OSC_PORT)
    for addr in osc_addresses():
        print("[osc_profile]   %s" % addr)
    return osc


def osc_profile_teardown() -> None:
    """Remove the OSC control nodes."""
    if not _in_td():
        return
    parent = op(PARENT)  # noqa: F821
    for name in (DAT_NAME, HANDLER_NAME):
        node = parent.op(name) if parent else None
        if node is not None:
            node.destroy()
            print("[osc_profile] removed " + name)


if _in_td():  # pragma: no cover - only inside TouchDesigner
    install_osc_profile_control()
