# audience_control.py -- the TouchDesigner half of the audience chat bridge
# =============================================================================
# WHAT THIS IS
#   The airlock the audience's votes arrive through, plus the Constant CHOP
#   they land in. It is the third of the four independent gates in the design,
#   and the only one that runs inside TouchDesigner.
#
#       install_audience_control()      # build fx_audience + wire the handler
#       audience_teardown()             # remove it; the rig returns to normal
#       panic()                         # known-good look, audience muted 5 min
#
# WHY THIS FILE EXISTS SEPARATELY FROM THE BRIDGE
#   The bridge process is NOT trusted. Not because it is likely to be
#   compromised, but because trusting it would make it the single point of
#   failure for every safety property. This file re-checks everything the
#   bridge already checked -- registry membership, scalar range, cooldowns, and
#   the photosensitivity ceiling -- against state it keeps itself. A hung,
#   rogue, or still-flushing bridge cannot get past it, and neither can a stray
#   packet from anything else on the LAN.
#
#   That is also why the ceiling numbers below are DUPLICATED from
#   chat_bridge/config.py rather than imported. The duplication is the point:
#   an independent check that shares its constants with the thing it is
#   checking is not independent. `tests/test_audience_osc.py` asserts the two
#   copies agree, so they cannot silently drift.
#
# THE ADDRESS SPLIT -- the single most important detail in this file
#   /dj/profile/<NAME>   Thomas. NEVER gated. Arms a 60 s audience lockout.
#   /dj/audience/...     the audience. Gated by everything below.
#   /dj/panic            Thomas. Known-good look + zero channels + 5 min mute.
#
#   If both used one address, the kill switch would also kill Thomas's own
#   control, which is the failure that makes a kill switch useless.
#
# FREEZE SAFETY
#   No audio tap. No CHOP Execute DAT. This is a DAT Execute on an OSC In DAT,
#   which fires when a packet arrives -- about once or twice a minute, not once
#   per FFT bin per frame. Writing a Constant CHOP channel and stamping a float
#   is all it does; every effect is then driven by parameter EXPRESSIONS that
#   TD evaluates once per cook. Nothing here can freeze the cook.
#
# NO AUDIO, EVER
#   Nothing in this file, and nothing in the bridge, opens an audio device,
#   synthesises speech, or touches the audio chain. TTS shoutouts are a
#   separate, later, optional piece of work and they route to their own output
#   device and their own OBS source. The reactivity source must never hear
#   anything but the music.
# =============================================================================

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

#: Audience address namespace. Distinct from OSC_PREFIX in osc_profile_control.
AUDIENCE_PREFIX = "/dj/audience"
#: Thomas's panic button.
PANIC_ADDRESS = "/dj/panic"

PARENT = "/project1"
CHOP_NAME = "fx_audience"

#: Nudge target -> fx_audience channel. Mirrors chat_bridge.config.NUDGE_CHANNEL.
NUDGE_CHANNEL: Dict[str, str] = {
    "GLOW": "gain_glow",
    "FLASH": "gain_flash",
    "TRAILS": "trail_bias",
    "SHAKE": "shake",
    "ZOOM": "zoom",
    "SPEED": "speed",
}

ONESHOT_TARGETS = ("STROBE_BURST", "COLOR_POP", "WHITEOUT")

#: Global per-verb cooldown, re-checked here. Matches the bridge's arbiter.
ACTION_COOLDOWN_S: Dict[str, float] = {
    "PROFILE": 60.0,
    "NUDGE": 10.0,
    "ONESHOT": 6.0,
}

#: Lockout lengths. A timer, not a mode, so it self-clears.
OPERATOR_LOCKOUT_S = 60.0
PANIC_LOCKOUT_S = 300.0

# =============================================================================
# THE PHOTOSENSITIVITY CEILING -- second, independent enforcement point
# =============================================================================
# Duplicated from chat_bridge/config.py on purpose (see the header). There is
# no OSC address that changes any of these, no argument that raises them, and
# no vote that removes them. A packet asking for a six-second strobe gets 1.5
# seconds; a second one arriving four seconds later gets dropped entirely.
ONESHOT_LIMITS: Dict[str, Tuple[float, float]] = {
    # target: (max duration seconds, min seconds between)
    "STROBE_BURST": (1.5, 20.0),
    "WHITEOUT": (0.6, 30.0),
    "COLOR_POP": (2.0, 8.0),
}


def _profiles() -> Any:
    """Import the profile registry, working both in TD and under pytest.

    Returns:
        The dj_graphics_profiles module.
    """
    import dj_graphics_profiles as gp

    return gp


def _colour_rgb(name: str) -> Optional[Tuple[float, float, float]]:
    """Resolve a colour NAME to the neon anchor the registry already defines.

    The audience cannot author an RGB triple; it can only name one of the
    anchors that already passed ``is_neon()`` and ``is_brown()``. This is the
    lookup that enforces that, and an unknown name resolves to None rather than
    to a default colour.

    Args:
        name: A colour name such as ``ACID``.

    Returns:
        The anchor, or None.
    """
    gp = _profiles()
    value = getattr(gp, name, None)
    if not isinstance(value, tuple) or len(value) != 3:
        return None
    if not all(isinstance(component, float) for component in value):
        return None
    if gp.is_brown(value) or not gp.is_neon(value):
        # Unreachable for the shipped anchors, and it stays unreachable: if
        # someone adds a muddy anchor later, the audience cannot reach it.
        return None
    return value


class AudienceState:
    """Everything the handler remembers between packets.

    Attributes:
        enabled: TD-side half of the kill switch. Independent of the bridge's
            own gate, so a hung or still-flushing bridge cannot get through.
        gain: Global scale on every audience scalar, 0..1.
        lock_profile: Audience keeps NUDGE and ONESHOT, loses PROFILE.
        lockout_until: Monotonic deadline. Thomas owns the look until then.
        current_profile: Last profile actually applied, for the log.
    """

    def __init__(self) -> None:
        self.enabled = True
        self.gain = 1.0
        self.lock_profile = False
        self.lockout_until = 0.0
        self.current_profile: Optional[str] = None
        self._verb_last: Dict[str, float] = {}
        self._oneshot_last: Dict[str, float] = {}
        self.rejected: Dict[str, int] = {}

    def reject(self, reason: str) -> None:
        """Count a rejection, so the log shows refusals rather than silence.

        Args:
            reason: Machine-readable reason.
        """
        self.rejected[reason] = self.rejected.get(reason, 0) + 1

    def locked_out(self, now: float) -> bool:
        """Report whether Thomas currently owns the look.

        Args:
            now: Monotonic seconds.

        Returns:
            True while a lockout is running.
        """
        return now < self.lockout_until

    def arm_lockout(self, now: float, seconds: float = OPERATOR_LOCKOUT_S) -> None:
        """Give Thomas the room.

        Args:
            now: Monotonic seconds.
            seconds: Lockout length.
        """
        self.lockout_until = max(self.lockout_until, now + seconds)

    def cooldown_ok(self, verb: str, now: float) -> bool:
        """Check the global per-verb cooldown.

        Args:
            verb: ``PROFILE`` / ``NUDGE`` / ``ONESHOT``.
            now: Monotonic seconds.

        Returns:
            True if enough time has passed.
        """
        last = self._verb_last.get(verb)
        if last is None:
            return True
        return now - last >= ACTION_COOLDOWN_S.get(verb, 0.0)

    def stamp(self, verb: str, now: float, target: Optional[str] = None) -> None:
        """Record that a verb was applied.

        Args:
            verb: The verb applied.
            now: Monotonic seconds.
            target: For one-shots, the target whose spacing is tracked.
        """
        self._verb_last[verb] = now
        if target is not None:
            self._oneshot_last[target] = now

    def ceiling_ok(self, target: str, now: float) -> Tuple[bool, float]:
        """Apply the photosensitivity ceiling, independently of the bridge.

        Args:
            target: A one-shot target.
            now: Monotonic seconds.

        Returns:
            ``(allowed, duration)`` where the duration is the CEILING. Nothing
            in the packet is consulted -- a requested duration is not read at
            all, so there is no value to get wrong.
        """
        limits = ONESHOT_LIMITS.get(target)
        if limits is None:
            return False, 0.0
        max_s, min_interval = limits
        last = self._oneshot_last.get(target)
        if last is not None and now - last < min_interval:
            return False, 0.0
        return True, max_s


#: Module-level singleton. The handler DAT re-executes per packet, but the
#: module stays imported, so this is what carries the cooldowns and the lockout
#: across packets.
STATE = AudienceState()


def _press(args: Optional[List[Any]]) -> bool:
    """Report whether an argument list reads as a button PRESS.

    Args:
        args: OSC arguments.

    Returns:
        False for a zero/false first argument (a release), True otherwise.
    """
    if not args:
        return True
    first = args[0]
    if isinstance(first, bool):
        return first
    if isinstance(first, (int, float)):
        return float(first) != 0.0
    return True


def _first_number(args: Optional[List[Any]], default: float = 0.0) -> float:
    """Read the first numeric argument, ignoring anything else.

    Args:
        args: OSC arguments.
        default: Returned when there is no usable number.

    Returns:
        A float.
    """
    if not args:
        return default
    first = args[0]
    if isinstance(first, bool) or not isinstance(first, (int, float)):
        return default
    value = float(first)
    if value != value or value in (float("inf"), float("-inf")):
        return default
    return value


def parse_audience_message(address: str, args: Optional[List[Any]] = None
                           ) -> Optional[Dict[str, Any]]:
    """Resolve an audience OSC message to a command, or None to ignore it.

    Pure and TD-free, exactly like ``parse_osc_profile_message`` -- the whole
    contract of an audience packet is decided here, not inside a callback that
    needs a running show to exercise.

    Ignoring is the default. Unknown address, unknown profile, unknown nudge
    target, unknown colour, non-finite number: all None. Profile membership is
    checked against the LIVE registry, not a list this file keeps.

    Args:
        address: The OSC address.
        args: OSC arguments.

    Returns:
        A command dict, or None. Commands are one of::

            {"kind": "profile",  "target": <registry key>}
            {"kind": "nudge",    "target": <NUDGE key>, "channel": ...,
             "amount": <clamped -1..1>}
            {"kind": "oneshot",  "target": <ONESHOT key>, "colour": <rgb|None>}
            {"kind": "control",  "control": "enable|gain|lock_profile",
             "value": float}
    """
    if not address:
        return None
    address = address.rstrip("/")

    if address == PANIC_ADDRESS or address.startswith(PANIC_ADDRESS + "/"):
        return {"kind": "panic"} if _press(args) else None

    if not address.startswith(AUDIENCE_PREFIX + "/"):
        return None
    rest = address[len(AUDIENCE_PREFIX) + 1:]
    if "/" not in rest:
        if rest in ("enable", "gain", "lock_profile"):
            return {"kind": "control", "control": rest,
                    "value": _first_number(args, 0.0)}
        return None

    verb, target = rest.split("/", 1)
    if "/" in target:
        return None

    if verb == "profile":
        gp = _profiles()
        if target not in gp.PROFILES or not _press(args):
            return None
        return {"kind": "profile", "target": target}

    if verb == "nudge":
        if target not in NUDGE_CHANNEL:
            return None
        amount = _first_number(args, 0.0)
        if amount == 0.0:
            return None
        return {"kind": "nudge", "target": target,
                "channel": NUDGE_CHANNEL[target],
                "amount": max(-1.0, min(1.0, amount))}

    if verb == "oneshot":
        if target not in ONESHOT_TARGETS:
            return None
        colour = None
        if target == "COLOR_POP":
            named = next((a for a in (args or []) if isinstance(a, str)), None)
            if named is None:
                return None
            colour = _colour_rgb(named)
            if colour is None:
                return None
        return {"kind": "oneshot", "target": target, "colour": colour}

    return None


def route(address: str, args: Optional[List[Any]] = None,
          state: Optional[AudienceState] = None,
          now: Optional[float] = None) -> Optional[Dict[str, Any]]:
    """Decide what a packet actually does, after every gate.

    This is the whole gating contract in one pure function, so the kill switch,
    the lockout, the cooldowns and the ceiling are all testable without
    TouchDesigner, TouchOSC, a network, or an audience.

    Args:
        address: OSC address.
        args: OSC arguments.
        state: State to consult and update. Defaults to the module singleton.
        now: Monotonic seconds. Defaults to the real clock.

    Returns:
        The command to execute, or None. Control and panic commands are
        applied to ``state`` here and returned for logging.
    """
    state = STATE if state is None else state
    now = time.monotonic() if now is None else now

    command = parse_audience_message(address, args)
    if command is None:
        return None

    kind = command["kind"]

    if kind == "panic":
        state.enabled = True
        state.arm_lockout(now, PANIC_LOCKOUT_S)
        return command

    if kind == "control":
        control, value = command["control"], command["value"]
        if control == "enable":
            state.enabled = bool(value)
        elif control == "gain":
            state.gain = max(0.0, min(1.0, value))
        elif control == "lock_profile":
            state.lock_profile = bool(value)
        return command

    # --- from here down it is audience traffic, and every gate applies -------
    if not state.enabled:
        state.reject("disabled")
        return None
    if state.locked_out(now):
        state.reject("operator_lockout")
        return None

    if kind == "profile":
        if state.lock_profile:
            state.reject("profile_locked")
            return None
        if not state.cooldown_ok("PROFILE", now):
            state.reject("cooldown_PROFILE")
            return None
        state.stamp("PROFILE", now)
        return command

    if kind == "nudge":
        if not state.cooldown_ok("NUDGE", now):
            state.reject("cooldown_NUDGE")
            return None
        state.stamp("NUDGE", now)
        command["amount"] = max(-1.0, min(1.0, command["amount"] * state.gain))
        return command

    if kind == "oneshot":
        if not state.cooldown_ok("ONESHOT", now):
            state.reject("cooldown_ONESHOT")
            return None
        allowed, duration = state.ceiling_ok(command["target"], now)
        if not allowed:
            state.reject("ceiling_%s" % command["target"])
            return None
        state.stamp("ONESHOT", now, command["target"])
        command["duration"] = duration
        return command

    return None  # pragma: no cover - kinds are exhaustive


def audience_addresses() -> List[str]:
    """List every OSC address this file accepts, for the docs and the layout.

    Returns:
        Addresses in a stable order.
    """
    gp = _profiles()
    out = [PANIC_ADDRESS]
    out += ["%s/%s" % (AUDIENCE_PREFIX, c)
            for c in ("enable", "gain", "lock_profile")]
    out += ["%s/profile/%s" % (AUDIENCE_PREFIX, name) for name in gp.PROFILES]
    out += ["%s/nudge/%s" % (AUDIENCE_PREFIX, t) for t in NUDGE_CHANNEL]
    out += ["%s/oneshot/%s" % (AUDIENCE_PREFIX, t) for t in ONESHOT_TARGETS]
    return out


# =============================================================================
# APPLY LAYER -- everything below needs a live TouchDesigner.
# =============================================================================


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


def _log(msg: str) -> None:
    """Print a namespaced line.

    Args:
        msg: The message body.
    """
    print("[audience] " + msg)


def _chop() -> Optional[Any]:
    """Resolve the fx_audience CHOP.

    Returns:
        The operator, or None if it has not been installed.
    """
    try:
        return op(PARENT + "/" + CHOP_NAME)  # noqa: F821 - TD global
    except Exception:
        return None


def _all_channels() -> Tuple[str, ...]:
    """Every channel fx_audience carries.

    Returns:
        Nudge channels followed by pulse channels.
    """
    gp = _profiles()
    return tuple(gp.AUDIENCE_CHANNELS) + tuple(gp.AUDIENCE_PULSE_CHANNELS)


def set_channel(name: str, value: float) -> bool:
    """Write one fx_audience channel.

    A Constant CHOP names its value parameters ``value0..valueN`` and its name
    parameters ``name0..nameN``, so the write is a lookup by declared order
    rather than by channel name.

    Args:
        name: Channel name.
        value: Value to write. Clamped to [-1, 1] for nudge channels; pulse
            stamps and durations are written as given, because they come from
            the ceiling, not from the packet.

    Returns:
        True if written.
    """
    node = _chop()
    if node is None:
        return False
    channels = _all_channels()
    if name not in channels:
        return False
    gp = _profiles()
    if name in gp.AUDIENCE_CHANNELS:
        value = max(-1.0, min(1.0, float(value)))
    index = channels.index(name)
    try:
        setattr(getattr(node.par, "value%d" % index), "val", float(value))
        return True
    except Exception as exc:
        _log("could not write %s: %s" % (name, exc))
        return False


def zero_channels() -> None:
    """Return every audience channel to its default.

    Nudges go to zero. Pulse stamps go far into the past so no window is open,
    which cancels an in-flight one-shot rather than waiting it out.
    """
    for name in _all_channels():
        set_channel(name, 0.0)
    for stamp in ("pop_t0", "strobe_t0", "white_t0"):
        set_channel(stamp, -1.0e9)


def apply_command(command: Dict[str, Any]) -> bool:
    """Execute a routed command against the live network.

    Args:
        command: The dict :func:`route` returned.

    Returns:
        True if something was applied.
    """
    gp = _profiles()
    kind = command["kind"]

    if kind == "panic":
        return panic()

    if kind == "control":
        _log("control %s = %s" % (command["control"], command["value"]))
        return True

    if kind == "profile":
        _log("-> %s" % command["target"])
        gp.apply_profile(command["target"])
        STATE.current_profile = command["target"]
        return True

    if kind == "nudge":
        return set_channel(command["channel"], command["amount"])

    if kind == "oneshot":
        target, duration = command["target"], command["duration"]
        stamp = _abs_seconds()
        if target == "STROBE_BURST":
            set_channel("strobe_dur", duration)
            return set_channel("strobe_t0", stamp)
        if target == "WHITEOUT":
            set_channel("white_dur", duration)
            return set_channel("white_t0", stamp)
        if target == "COLOR_POP":
            red, green, blue = command["colour"]
            set_channel("pop_r", red)
            set_channel("pop_g", green)
            set_channel("pop_b", blue)
            set_channel("pop_dur", duration)
            return set_channel("pop_t0", stamp)
    return False


def _abs_seconds() -> float:
    """Read TD's absolute time, which is the clock the expressions use.

    Returns:
        ``absTime.seconds``, or 0.0 outside TouchDesigner.
    """
    try:
        return float(absTime.seconds)  # noqa: F821 - TD global
    except Exception:
        return 0.0


def panic() -> bool:
    """Known-good look, every audience channel zeroed, five minutes of quiet.

    One tap. It does not depend on the bridge being healthy, does not depend on
    the network being healthy, and does not need anything to be re-enabled
    afterwards.

    Returns:
        True.
    """
    gp = _profiles()
    _log("PANIC -- restoring %s and muting the audience for %d s"
         % (gp.DEFAULT_PROFILE, PANIC_LOCKOUT_S))
    zero_channels()
    gp.apply_profile(gp.DEFAULT_PROFILE)
    STATE.current_profile = gp.DEFAULT_PROFILE
    return True


def handle(address: str, args: Optional[List[Any]] = None) -> Optional[Dict[str, Any]]:
    """Route a packet and apply whatever survives.

    Args:
        address: OSC address.
        args: OSC arguments.

    Returns:
        The applied command, or None.
    """
    command = route(address, args)
    if command is None:
        return None
    apply_command(command)
    return command


def install_audience_control() -> Optional[Any]:
    """Create fx_audience and rebind the profile expressions to use it. Idempotent.

    The CHOP's ABSENCE is the strongest kill switch there is: without it, every
    expression is emitted in its original form and there is no term for the
    audience to write into at all. Installing it is therefore the deliberate
    act that opens the door, and ``audience_teardown()`` closes it completely.

    Returns:
        The Constant CHOP, or None outside TouchDesigner.
    """
    if not _in_td():
        _log("not inside TouchDesigner -- nothing installed")
        return None
    parent = op(PARENT)  # noqa: F821
    if parent is None:
        _log("%s not found" % PARENT)
        return None

    gp = _profiles()
    node = parent.op(CHOP_NAME) or parent.create(constantCHOP, CHOP_NAME)  # noqa: F821
    node.nodeX, node.nodeY = 500, -900
    channels = _all_channels()
    try:
        node.par.name0.sequence.numBlocks = len(channels)
    except Exception:
        pass
    for i, name in enumerate(channels):
        try:
            setattr(getattr(node.par, "name%d" % i), "val", name)
            setattr(getattr(node.par, "value%d" % i), "val", 0.0)
        except Exception as exc:
            _log("channel %d (%s): %s" % (i, name, exc))
    zero_channels()

    # Re-apply the current look so every expression picks up its audience form.
    current = STATE.current_profile or gp.selected_profile()
    gp.apply_profile(current)
    _log("installed: %d channels, %s rebound with audience terms"
         % (len(channels), current))
    for addr in audience_addresses():
        _log("  %s" % addr)
    return node


def audience_teardown() -> None:
    """Remove fx_audience and rebind the look without any audience term."""
    if not _in_td():
        return
    gp = _profiles()
    zero_channels()
    parent = op(PARENT)  # noqa: F821
    node = parent.op(CHOP_NAME) if parent else None
    if node is not None:
        node.destroy()
        _log("removed " + CHOP_NAME)
    gp.apply_profile(STATE.current_profile or gp.selected_profile())
    _log("expressions rebound without audience terms")
