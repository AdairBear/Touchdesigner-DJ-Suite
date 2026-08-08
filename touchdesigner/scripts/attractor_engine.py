# attractor_engine.py -- the chaotic-attractor engine as a DJ_Graphics profile
# =============================================================================
# WHAT THIS IS
#   The bridge between `attractor_math.py` (pure ODEs) and the live rig. Three
#   things live here:
#
#     1. AttractorSpec -- the per-profile knob set, exactly analogous to the
#        reactivity fields on `dj_graphics_profiles.Profile`.
#     2. The parameter-EXPRESSION builders that drive those knobs from audio,
#        from the DJ, and (for a whitelisted two of them) from the audience.
#     3. `cook(scriptOp)` -- what the Script CHOP calls once per cook.
#
#   `attractor_pipeline.py` builds the nodes. `dj_graphics_profiles.py` owns
#   the registry and applies the plan. This file owns the numbers and the
#   strings, and is importable and testable with no TouchDesigner.
#
# -----------------------------------------------------------------------------
# HOW THIS OBEYS THE EXISTING SAFETY MODEL (read this before changing a number)
#
#   The rig already has a four-gate audience model and three hard caps. This
#   engine does not add a fifth gate or a parallel path -- it plugs into the
#   ones that exist:
#
#   * FREEZE SAFETY. `cook()` is a Script CHOP onCook -- once per cook, exactly
#     like `fx_palette_engine`. It is NOT a CHOP Execute onValueChange, which
#     is what fired once per FFT bin and froze the show. It adds NO audio tap:
#     every audio value it uses arrives through a parameter expression reading
#     the envelope CHOPs that already exist. The per-cook cost is bounded at
#     construction by ATTRACTOR_MAX_POINTS, not by anything a control can move.
#
#   * THE CHAOS KNOB IS THE CAP. Every chaos value in this system is a
#     NORMALISED 0..1 that `attractor_math` maps onto a per-system interval
#     chosen to stay on the strange attractor. There is no code path that
#     accepts a raw rho, b or a. An audience nudge of 999 is 1.0 is the top of
#     a range that was already validated. That is the same shape as
#     GLOW_SIZE_HARD_CAP: the cap is structural, not checked.
#
#   * THE AUDIENCE SURFACE IS TWO CHANNELS, BOTH SUMMED INSIDE THE MIN.
#     `chaos` and `morph_bias`, plus the `speed` channel the rig already has.
#     Both new terms are `max(-1, min(1, ...)) * span` and both are summed
#     INSIDE the clamp, never alongside it -- see `chaos_expr` and `morph_expr`.
#     Everything else the attractor inherits (glow, flash, trails, shake, zoom,
#     colour pop) it inherits because it renders THROUGH the existing fx_ chain,
#     so it is governed by the existing clamps with no new code at all.
#
#   * THE AUDIENCE CANNOT PICK A FORM. ATTRACTOR_MORPH_SPAN is 0.35 and one
#     whole form is 1.0 of morph position, so a fully-driven audience bias
#     slides the blend without ever selecting an attractor. Selecting one is a
#     profile change or a `/dj/attractor/morph` tap, and both are Thomas's.
#
#   * PHOTOSENSITIVITY. This engine emits no flashes of its own. Its brightness
#     reaches the frame through `fx_kick_bright`, whose expression already
#     carries the STROBE_HZ_CAP ceiling. There is deliberately nothing here
#     that can flash, so there is nothing here that can raise the ceiling.
#
#   * OPT-IN, LIKE EVERYTHING ELSE. `audience=False` is the default on every
#     builder. With no `fx_audience` CHOP installed, every string this file
#     emits is byte-identical to the DJ-only form, and `tests/` asserts that
#     rather than arguing it.
#
# -----------------------------------------------------------------------------
# THE COST MODEL, MEASURED
#   Per cook: `seeds * substeps` RK4 steps in pure Python, plus a write of
#   `seeds * trail` floats into four channels. Both factors are fixed by
#   ATTRACTOR_MAX_SEEDS / ATTRACTOR_MAX_TRAIL / ATTRACTOR_MAX_POINTS at
#   construction. No live control -- DJ or audience -- can make this allocate
#   or make it iterate more. Raising `speed` buys substeps, and substeps are
#   capped too.
#
#   Measured on this Mac (python3.14, pure Python, no numpy), against the
#   33.3 ms budget of a 30 fps cook:
#       absolute worst case  16384 points, 8 substeps   ~2.7 ms
#       heaviest shipped     ATTRACTOR_AIZAWA, speed 2   ~1.4 ms
#   Re-measure rather than assume if these caps are ever raised. The number
#   that matters is not the average, it is the worst thing a fader can ask for.
# =============================================================================

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import attractor_math as am

# =============================================================================
# HARD BOUNDS
# =============================================================================
#: Trajectories integrated in parallel. 64 * 8 substeps = 512 RK4 steps per
#: cook, which measures in single-digit milliseconds of pure Python.
ATTRACTOR_MAX_SEEDS = 64
#: Points remembered per trajectory.
ATTRACTOR_MAX_TRAIL = 512
#: Instanced sprites drawn. Enforced as a PRODUCT so no combination of the two
#: caps above can multiply past what the channel write can afford.
ATTRACTOR_MAX_POINTS = 16384
#: RK4 substeps per cook. This is what `speed` buys instead of instability.
ATTRACTOR_MAX_SUBSTEPS = 8
#: Speed multiplier on the normalised field. Past this the trail is a dotted
#: line rather than a curve, because consecutive points stop being adjacent.
ATTRACTOR_SPEED_HARD_CAP = 3.0
ATTRACTOR_SPEED_FLOOR = 0.05
#: Normalised-units-to-frame scale on the Geometry COMP.
ATTRACTOR_SPREAD_HARD_CAP = 2.0
#: Sprite radius, in world units of the render camera.
ATTRACTOR_SIZE_HARD_CAP = 0.05
#: Auto-rotation, degrees per second. Fast enough to read as 3D, slow enough
#: not to be a strobe by another name.
ATTRACTOR_SPIN_HARD_CAP = 24.0
#: The chaos knob is normalised, so its cap is 1.0 by construction. Named
#: anyway, because a test that asserts against a literal is a test that stops
#: meaning anything the day the literal moves.
ATTRACTOR_CHAOS_HARD_CAP = 1.0

# =============================================================================
# THE AUDIENCE SURFACE -- two channels, and that is the whole list
# =============================================================================
#: New fx_audience channels this engine adds. `dj_graphics_profiles` appends
#: these to AUDIENCE_CHANNELS, `audience_control` maps NUDGE targets onto them,
#: and `chat_bridge.config` lists the targets. All four are asserted to agree.
ATTRACTOR_AUDIENCE_CHANNELS: Tuple[str, ...] = ("chaos", "morph_bias")

#: Existing fx_audience channels this engine also reads. Named here so `aud()`
#: can validate a channel without importing `dj_graphics_profiles` (which
#: imports this module -- the dependency runs one way only). The tests assert
#: this is a subset of the real registry, so a rename there fails loudly here.
SHARED_AUDIENCE_CHANNELS: Tuple[str, ...] = ("speed",)

#: How far one full unit of nudge may move each knob.
ATTRACTOR_CHAOS_SPAN = 0.20     # of the normalised 0..1 chaos range
ATTRACTOR_MORPH_SPAN = 0.35     # of one whole form (1.0) -- see the header
ATTRACTOR_SPEED_SPAN = 0.50     # of the speed multiplier

#: Duplicated from `dj_graphics_profiles` on purpose, the same way
#: `audience_control` duplicates the photosensitivity limits: a module that
#: shares its constants with the thing it plugs into cannot be checked against
#: it. `tests/test_attractor_engine.py` asserts the copies agree.
AUDIENCE_CHOP = "fx_audience"
KICK = "op('fx_kick_env')['bass']"
SNARE = "op('fx_snare_env')['high']"
ENERGY = "op('fx_master')['bass']"

#: The engine's own control CHOPs. `attr_ctl` carries the resolved knobs (its
#: numeric parameters hold the EXPRESSIONS built below). `attr_dj` carries
#: Thomas's live offsets, written by OSC.
CTL_CHOP = "attr_ctl"
DJ_CHOP = "attr_dj"

#: attr_ctl channel order. `enable`, `seeds` and `trail_len` are plain values
#: written by the profile; everything else is expression-driven.
CTL_CHANNELS: Tuple[str, ...] = (
    "enable", "chaos", "morph", "speed", "trail", "spread", "size", "spin",
    "seeds", "trail_len",
)

#: attr_dj channel order. Thomas's offsets, summed INSIDE the same clamps the
#: audience terms are summed inside -- one control surface, one set of caps.
DJ_CHANNELS: Tuple[str, ...] = ("chaos", "morph", "speed", "trail", "spread")

#: How far one unit of DJ offset moves each knob. Wider than the audience's,
#: which is the entire difference between the two roles.
DJ_SPAN: Dict[str, float] = {
    "chaos": 1.0,
    "morph": 3.0,
    "speed": 2.0,
    "trail": 1.0,
    "spread": 1.0,
}


# =============================================================================
# THE SPEC -- what a profile declares about its attractor
# =============================================================================


class AttractorSpec:
    """One profile's attractor configuration.

    Every field is a plain number or string. Applying a spec writes values and
    binds parameter expressions; it never creates or deletes a node, exactly
    like the rest of the profile system.

    Attributes:
        system: Starting form -- a key of ``attractor_math.SEQUENCE``, or
            ``"MORPH"`` to start mid-sequence and keep moving.
        seeds: Trajectories integrated in parallel. Clamped on read.
        trail: Points remembered per trajectory. Clamped on read.
        chaos_base: Normalised 0..1 chaos in silence.
        chaos_energy_gain: How much the 30 s energy accumulator opens the chaos
            knob in a busy section. The form breathes with the track.
        chaos_kick_gain: Chaos added at full kick. Short and percussive.
        morph_cycle_s: Seconds per form when the morph advances on the clock.
            0 pins the form and leaves only the energy term and the taps.
        morph_energy_gain: How far a full-energy section pushes the morph. This
            is the "morph on a drop" behaviour: the form leans toward the next
            attractor as a section builds and settles back as it empties, with
            no state, no threshold and no onset detector to mistune.
        speed_base: Speed multiplier in silence.
        speed_kick_gain: Speed added at full kick.
        trail_base: 0..1. Higher keeps the tail visible for longer.
        trail_snare_gain: Tail shortening at full snare, so hats chop the tail.
        spread: Normalised-units-to-frame scale.
        size: Sprite radius.
        spin: Auto-rotation in degrees per second.
    """

    def __init__(
        self,
        system: str = "MORPH",
        seeds: int = 24,
        trail: int = 256,
        chaos_base: float = 0.25,
        chaos_energy_gain: float = 0.30,
        chaos_kick_gain: float = 0.15,
        morph_cycle_s: float = 0.0,
        morph_energy_gain: float = 0.60,
        speed_base: float = 1.0,
        speed_kick_gain: float = 0.35,
        trail_base: float = 0.55,
        trail_snare_gain: float = 0.25,
        spread: float = 0.85,
        size: float = 0.012,
        spin: float = 6.0,
    ) -> None:
        self.system = str(system)
        self.seeds = int(seeds)
        self.trail = int(trail)
        self.chaos_base = float(chaos_base)
        self.chaos_energy_gain = float(chaos_energy_gain)
        self.chaos_kick_gain = float(chaos_kick_gain)
        self.morph_cycle_s = float(morph_cycle_s)
        self.morph_energy_gain = float(morph_energy_gain)
        self.speed_base = float(speed_base)
        self.speed_kick_gain = float(speed_kick_gain)
        self.trail_base = float(trail_base)
        self.trail_snare_gain = float(trail_snare_gain)
        self.spread = float(spread)
        self.size = float(size)
        self.spin = float(spin)

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return "<AttractorSpec %s seeds=%d trail=%d>" % (
            self.system, self.seeds, self.trail)


def morph_base(spec: AttractorSpec) -> float:
    """Resolve a spec's starting morph position.

    Args:
        spec: The spec.

    Returns:
        The index of ``spec.system`` in the morph sequence, or 0.0 for
        ``"MORPH"`` (which starts on Lorenz and keeps going).
    """
    if spec.system in am.SEQUENCE:
        return float(am.SEQUENCE.index(spec.system))
    return 0.0


def resolve_counts(seeds: Any, trail: Any) -> Tuple[int, int]:
    """Clamp a requested seed/trail pair into the hard bounds.

    Enforced as a PRODUCT as well as individually, because the per-cook channel
    write scales with ``seeds * trail`` and two individually-legal numbers can
    multiply into something that is not.

    Args:
        seeds: Requested trajectory count.
        trail: Requested points per trajectory.

    Returns:
        ``(seeds, trail)``, both at least 2 and never exceeding the caps or
        their product cap. Trail is what gives, because losing tail length is
        less visible than losing half the trajectories.
    """
    def _whole(raw: Any, fallback: int) -> int:
        """Coerce a CHOP read to an int without ever raising.

        These arrive from `_read`, which means they can be anything a Constant
        CHOP parameter can hold -- including inf, which `int()` does not merely
        reject but raises OverflowError on.
        """
        try:
            value = float(raw)
        except (TypeError, ValueError):
            return fallback
        if value != value or value in (float("inf"), float("-inf")):
            return fallback
        return int(value)

    n_seeds = _whole(seeds, 1)
    n_trail = _whole(trail, 2)
    n_seeds = max(1, min(ATTRACTOR_MAX_SEEDS, n_seeds))
    n_trail = max(2, min(ATTRACTOR_MAX_TRAIL, n_trail))
    if n_seeds * n_trail > ATTRACTOR_MAX_POINTS:
        n_trail = max(2, ATTRACTOR_MAX_POINTS // n_seeds)
    return n_seeds, n_trail


def validate_spec(spec: AttractorSpec) -> List[str]:
    """Check a spec against the engine's bounds.

    Args:
        spec: The spec to check.

    Returns:
        A list of human-readable problems. Empty means the spec is valid.
    """
    problems: List[str] = []
    if spec.system != "MORPH" and spec.system not in am.SEQUENCE:
        problems.append("system %r must be MORPH or one of %s"
                        % (spec.system, list(am.SEQUENCE)))
    if not 0.0 <= spec.chaos_base <= 1.0:
        problems.append("chaos_base %.3f must be within 0..1 (it is normalised)"
                        % spec.chaos_base)
    if not 0.0 <= spec.trail_base <= 1.0:
        problems.append("trail_base %.3f must be within 0..1" % spec.trail_base)
    if spec.speed_base <= 0.0:
        problems.append("speed_base must be > 0")
    if spec.speed_base > ATTRACTOR_SPEED_HARD_CAP:
        problems.append("speed_base %.2f exceeds the hard cap %.2f"
                        % (spec.speed_base, ATTRACTOR_SPEED_HARD_CAP))
    if spec.spread <= 0.0 or spec.spread > ATTRACTOR_SPREAD_HARD_CAP:
        problems.append("spread %.2f must be within 0..%.2f"
                        % (spec.spread, ATTRACTOR_SPREAD_HARD_CAP))
    if spec.size <= 0.0 or spec.size > ATTRACTOR_SIZE_HARD_CAP:
        problems.append("size %.4f must be within 0..%.4f"
                        % (spec.size, ATTRACTOR_SIZE_HARD_CAP))
    if abs(spec.spin) > ATTRACTOR_SPIN_HARD_CAP:
        problems.append("spin %.1f exceeds the hard cap %.1f deg/s"
                        % (spec.spin, ATTRACTOR_SPIN_HARD_CAP))
    if spec.morph_cycle_s < 0.0:
        problems.append("morph_cycle_s must be >= 0 (0 pins the form)")
    for field in ("chaos_energy_gain", "chaos_kick_gain", "morph_energy_gain",
                  "speed_kick_gain", "trail_snare_gain"):
        if getattr(spec, field) < 0.0:
            problems.append("%s must be >= 0" % field)
    resolved = resolve_counts(spec.seeds, spec.trail)
    if resolved != (spec.seeds, spec.trail):
        problems.append("seeds/trail %s would be clamped to %s -- declare the "
                        "clamped values so the profile says what it does"
                        % ((spec.seeds, spec.trail), resolved))
    return problems


# =============================================================================
# EXPRESSION BUILDERS -- pure strings, every one of them clamped
# =============================================================================


def aud(channel: str) -> str:
    """Reference one fx_audience channel from a parameter expression.

    Args:
        channel: A member of ATTRACTOR_AUDIENCE_CHANNELS or
            SHARED_AUDIENCE_CHANNELS.

    Returns:
        A TD expression fragment.

    Raises:
        KeyError: On an unknown channel, so a typo fails at build time rather
            than binding a dead reference at the rig. Same discipline as
            ``dj_graphics_profiles.aud``.
    """
    if channel not in ATTRACTOR_AUDIENCE_CHANNELS + SHARED_AUDIENCE_CHANNELS:
        raise KeyError("no such fx_audience channel for the attractor: %r" % channel)
    return "op('%s')['%s']" % (AUDIENCE_CHOP, channel)


def aud_term(channel: str, span: float) -> str:
    """Build one clamped audience term.

    The value is clamped to [-1, 1] here, in the expression itself, before it
    is scaled -- the fourth and last of the four independent clamps a nudge
    passes through. Each is sufficient alone; four exist so that none has to be
    trusted.

    Args:
        channel: fx_audience channel name.
        span: How far one full unit of nudge may move the knob.

    Returns:
        A TD expression fragment worth at most ``span`` in absolute value.
    """
    return "max(-1, min(1, %s)) * %g" % (aud(channel), span)


def dj(channel: str) -> str:
    """Reference one attr_dj channel from a parameter expression.

    Args:
        channel: A member of DJ_CHANNELS.

    Returns:
        A TD expression fragment.

    Raises:
        KeyError: On an unknown channel.
    """
    if channel not in DJ_CHANNELS:
        raise KeyError("no such attr_dj channel: %r" % channel)
    return "op('%s')['%s']" % (DJ_CHOP, channel)


def dj_term(channel: str) -> str:
    """Build one clamped DJ-offset term.

    Clamped for the same reason the audience term is: a stray OSC float from
    anything else on the LAN reaches this parameter through the same door.
    Thomas's span is simply wider.

    Args:
        channel: attr_dj channel name.

    Returns:
        A TD expression fragment worth at most ``DJ_SPAN[channel]``.
    """
    span = DJ_SPAN[channel]
    return "max(-1, min(1, %s)) * %g" % (dj(channel), span)


def chaos_expr(spec: AttractorSpec, audience: bool = False) -> str:
    """Build the normalised chaos expression, always clamped to 0..1.

    THE CAP IS THE RANGE. `attractor_math` maps 0..1 onto each system's own
    safe parameter interval, so there is no value of this expression that
    reaches an unsafe rho, b or a. The audience term is summed INSIDE the
    ``min(max(..., 0), 1)``, never beside it.

    Args:
        spec: Source of the base and the audio gains.
        audience: True to include the clamped fx_audience term.

    Returns:
        A TD parameter expression string, provably within 0..1.
    """
    drive = "%g + (%s - 1.0) * %g + %s * %g + %s" % (
        spec.chaos_base, ENERGY, spec.chaos_energy_gain,
        KICK, spec.chaos_kick_gain, dj_term("chaos"),
    )
    if audience:
        drive += " + %s" % aud_term("chaos", ATTRACTOR_CHAOS_SPAN)
    return "min(max(%s, 0), %g)" % (drive, ATTRACTOR_CHAOS_HARD_CAP)


def morph_expr(spec: AttractorSpec, audience: bool = False) -> str:
    """Build the cyclic morph-position expression.

    Deliberately NOT clamped: morph is cyclic and `attractor_math.morph_pair`
    takes it modulo the sequence length, so every real number is a valid,
    bounded form. What IS bounded is the audience's authority over it --
    ATTRACTOR_MORPH_SPAN is 0.35 against a whole form of 1.0, so a fully driven
    bias slides the blend and can never select an attractor.

    The energy term is the section cue: `fx_master` is the existing 30 s
    beat-density accumulator mapped to roughly 0.6..1.5, so a section that
    builds leans the form toward the next attractor and a section that empties
    lets it settle back. No onset detector, no threshold, no state to desync.

    Args:
        spec: Source of the base, the cycle and the energy gain.
        audience: True to include the clamped fx_audience term.

    Returns:
        A TD parameter expression string.
    """
    terms = ["%g" % morph_base(spec)]
    if spec.morph_cycle_s > 0.0:
        terms.append("int(absTime.seconds / %g)" % spec.morph_cycle_s)
    terms.append("(%s - 1.0) * %g" % (ENERGY, spec.morph_energy_gain))
    terms.append(dj_term("morph"))
    if audience:
        terms.append(aud_term("morph_bias", ATTRACTOR_MORPH_SPAN))
    return " + ".join(terms)


def speed_expr(spec: AttractorSpec, audience: bool = False) -> str:
    """Build the speed-multiplier expression, clamped to the engine's window.

    The floor matters as much as the ceiling: a speed of zero freezes the
    trajectory and the trail decays to a dot, which reads as a crash rather
    than as an effect.

    Args:
        spec: Source of the base and the kick gain.
        audience: True to include the clamped fx_audience term, which reuses
            the rig's existing ``speed`` channel rather than adding another --
            "SPEED" already means "make it go faster" to the audience, and it
            should mean that here too.

    Returns:
        A TD parameter expression string within
        ``ATTRACTOR_SPEED_FLOOR..ATTRACTOR_SPEED_HARD_CAP``.
    """
    drive = "%g + %s * %g + %s" % (
        spec.speed_base, KICK, spec.speed_kick_gain, dj_term("speed"))
    if audience:
        drive += " + %s" % aud_term("speed", ATTRACTOR_SPEED_SPAN)
    return "min(max(%s, %g), %g)" % (
        drive, ATTRACTOR_SPEED_FLOOR, ATTRACTOR_SPEED_HARD_CAP)


def trail_expr(spec: AttractorSpec) -> str:
    """Build the tail-length expression, clamped to 0..1.

    DJ and audio only. The audience already reaches the visible tail through
    the existing ``trail_bias`` nudge on `fx_trail_hsv`, and giving them a
    second, differently-clamped route to the same visual property would be two
    caps where the design has one.

    Args:
        spec: Source of the base and the snare gain.

    Returns:
        A TD parameter expression string within 0..1.
    """
    return "min(max(%g - %s * %g + %s, 0), 1)" % (
        spec.trail_base, SNARE, spec.trail_snare_gain, dj_term("trail"))


def spread_expr(spec: AttractorSpec) -> str:
    """Build the frame-scale expression, clamped to the hard cap.

    Args:
        spec: Source of the base spread.

    Returns:
        A TD parameter expression string.
    """
    return "min(max(%g + %s, 0.05), %g)" % (
        spec.spread, dj_term("spread"), ATTRACTOR_SPREAD_HARD_CAP)


def size_expr(spec: AttractorSpec) -> str:
    """Build the sprite-radius expression.

    A plain clamped literal: sprite size is a look decision, not a reactive
    one, and a size that pumped with the kick would double up on the flash and
    the zoom that already do.

    Args:
        spec: Source of the size.

    Returns:
        A TD parameter expression string.
    """
    return "min(max(%g, 0.001), %g)" % (spec.size, ATTRACTOR_SIZE_HARD_CAP)


def spin_expr(spec: AttractorSpec) -> str:
    """Build the auto-rotation expression, in degrees.

    A steady turn, so the 3D structure reads as 3D on a 2D stream. Bounded by
    ATTRACTOR_SPIN_HARD_CAP because a fast enough rotation of a high-contrast
    form is a flicker, and flicker is the one thing this rig does not improvise
    with.

    Args:
        spec: Source of the spin rate.

    Returns:
        A TD parameter expression string.
    """
    rate = max(-ATTRACTOR_SPIN_HARD_CAP, min(ATTRACTOR_SPIN_HARD_CAP, spec.spin))
    return "absTime.seconds * %g" % rate


def attr_ctl_plan(spec: AttractorSpec, audience: bool = False,
                  enable: bool = True) -> Dict[str, Any]:
    """Describe every attr_ctl channel a spec would drive.

    Args:
        spec: The spec.
        audience: Whether to emit the audience-aware forms.
        enable: False emits a dark attractor -- which is what every
            non-attractor profile writes, so switching away from the attractor
            turns it off rather than leaving it running behind the silhouette.

    Returns:
        A dict of channel -> value (plain number) or expression (string).
    """
    seeds, trail = resolve_counts(spec.seeds, spec.trail)
    return {
        "enable": 1.0 if enable else 0.0,
        "chaos": chaos_expr(spec, audience),
        "morph": morph_expr(spec, audience),
        "speed": speed_expr(spec, audience),
        "trail": trail_expr(spec),
        "spread": spread_expr(spec),
        "size": size_expr(spec),
        "spin": spin_expr(spec),
        "seeds": float(seeds),
        "trail_len": float(trail),
    }


def dark_ctl_plan() -> Dict[str, Any]:
    """Describe the attr_ctl state a profile with NO attractor writes.

    Plain values, no expressions, so a non-attractor profile leaves nothing
    bound that could still be evaluated -- and `cook()` short-circuits on
    ``enable == 0`` before it integrates anything, so the engine costs nothing
    while UV_RAVE is up.

    Returns:
        A dict of channel -> value.
    """
    return {name: 0.0 for name in CTL_CHANNELS}


# =============================================================================
# THE SCRIPT CHOP -- one cook, bounded work, no audio tap
# =============================================================================

#: Module-level engine state. The callback DAT re-executes per cook but the
#: module stays imported, which is what carries the ring buffer across frames
#: -- the same reason `audience_control.STATE` is a module singleton.
_BUFFER: Optional[am.TrailBuffer] = None
_SHAPE: Tuple[int, int] = (0, 0)
_TICK = 0

#: Last cook's diagnostics. Read by `attractor_stats()`. The escape count is
#: the fail-loud signal: a count that stays nonzero frame after frame means a
#: parameter window is wrong, and nothing else will tell you.
STATS: Dict[str, Any] = {"escapes": 0, "escapes_total": 0, "points": 0,
                         "substeps": 0, "cooks": 0}

#: Escapes per cook above which the engine complains to the Textport. One or
#: two on a morph boundary is normal; a steady stream is a bug.
ESCAPE_ALERT_PER_COOK = 4
#: Do not print the complaint more than once per this many cooks.
ESCAPE_ALERT_EVERY = 300


def _read(chop: Any, channel: str, default: float) -> float:
    """Read one channel from a CHOP, tolerating its absence.

    Args:
        chop: The CHOP, or None.
        channel: Channel name.
        default: Returned when the CHOP or the channel is missing, or when the
            value is not finite.

    Returns:
        A finite float.
    """
    if chop is None:
        return default
    try:
        value = float(chop[channel].eval())
    except Exception:
        return default
    if value != value or value in (float("inf"), float("-inf")):
        return default
    return value


def _frame_dt() -> float:
    """Frame duration in seconds, from the project's cook rate.

    Returns:
        Seconds per cook, defaulting to 1/30 -- the rate the rig runs at, and
        a safe assumption outside TouchDesigner.
    """
    try:
        rate = float(project.cookRate)  # noqa: F821 - TD global
        if rate > 0.0:
            return 1.0 / rate
    except Exception:
        pass
    return 1.0 / 30.0


def cook(scriptOp: Any) -> None:
    """Advance the attractor and emit the point cloud. Script CHOP onCook.

    FREEZE SAFETY: this is onCook -- once per cook. It is not, and must never
    become, a CHOP Execute onValueChange. It reads three control channels and
    does a bounded amount of arithmetic; it opens no audio device and taps no
    spectrum.

    Args:
        scriptOp: The Script CHOP TouchDesigner passes in.
    """
    global _BUFFER, _SHAPE, _TICK

    scriptOp.clear()
    ctl = _op(CTL_CHOP)

    if _read(ctl, "enable", 0.0) <= 0.0:
        # A non-attractor profile is up. Emit one silent sample rather than
        # zero: a Script CHOP with no samples makes downstream instancing
        # complain, and a complaint per cook is noise that hides real ones.
        for name in ("tx", "ty", "tz", "fade"):
            scriptOp.appendChan(name).vals = [0.0]
        return

    seeds, trail = resolve_counts(_read(ctl, "seeds", 24.0),
                                  _read(ctl, "trail_len", 256.0))
    chaos = min(1.0, max(0.0, _read(ctl, "chaos", 0.25)))
    morph = _read(ctl, "morph", 0.0)
    speed = min(ATTRACTOR_SPEED_HARD_CAP,
                max(ATTRACTOR_SPEED_FLOOR, _read(ctl, "speed", 1.0)))
    tail = min(1.0, max(0.0, _read(ctl, "trail", 0.55)))

    if _BUFFER is None or _SHAPE != (seeds, trail):
        _BUFFER = am.TrailBuffer(seeds, trail, morph)
        _SHAPE = (seeds, trail)

    dt = _frame_dt()
    substeps = am.substeps_for(dt, speed, morph, ATTRACTOR_MAX_SUBSTEPS)
    _TICK += 1
    escapes = _BUFFER.advance(dt, speed, morph, chaos, substeps, _TICK)

    # Longer tail == flatter falloff. Gamma 4 is a short comet, 0.5 is a ribbon
    # that reaches all the way back to the oldest slot.
    gamma = 4.0 - 3.5 * tail
    fades = _BUFFER.fades(gamma)

    scriptOp.appendChan("tx").vals = _BUFFER.xs
    scriptOp.appendChan("ty").vals = _BUFFER.ys
    scriptOp.appendChan("tz").vals = _BUFFER.zs
    scriptOp.appendChan("fade").vals = fades

    STATS["escapes"] = escapes
    STATS["escapes_total"] += escapes
    STATS["points"] = seeds * trail
    STATS["substeps"] = substeps
    STATS["cooks"] += 1
    if escapes >= ESCAPE_ALERT_PER_COOK and STATS["cooks"] % ESCAPE_ALERT_EVERY == 1:
        # Fail loud. A silently-reseeding engine looks like a working engine
        # right up until the form stops being the form.
        print("[attractor] WARN %d seeds reseeded this cook (chaos=%.2f "
              "morph=%.2f speed=%.2f). A parameter window is probably wrong."
              % (escapes, chaos, morph, speed))


def attractor_stats() -> Dict[str, Any]:
    """Return the last cook's diagnostics.

    Returns:
        A copy of :data:`STATS`.
    """
    return dict(STATS)


def reset_engine() -> None:
    """Drop the ring buffer so the next cook rebuilds it from a fresh seed."""
    global _BUFFER, _SHAPE
    _BUFFER = None
    _SHAPE = (0, 0)


#: Where the control CHOPs live when a relative lookup misses. Matches PARENT
#: in `dj_graphics_profiles` and `audience_control`.
PARENT = "/project1"


def _op(name: str) -> Optional[Any]:
    """Resolve a node by name, returning None outside TD or when absent.

    Tries the relative name first (correct when the callback DAT sits beside
    the CHOPs) and falls back to the absolute path. Both, rather than one,
    because `cook()` is called from a generated DAT whose parent is a build
    detail this module should not have to know.

    Args:
        name: Node name.

    Returns:
        The operator, or None.
    """
    for path in (name, PARENT + "/" + name):
        try:
            node = op(path)  # noqa: F821 - TD global
        except Exception:
            return None
        if node is not None:
            return node
    return None


# =============================================================================
# THE CALLBACK DAT
#
# Deliberately thin. The integrator is 300 lines of arithmetic that wants unit
# tests, and code that lives inside a generated string cannot have them. So the
# DAT delegates, exactly the way `osc_profile_control.HANDLER_CODE` does.
# =============================================================================

SCRIPTS_DIR = "/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts"

ENGINE_CALLBACK_CODE = '''# attr_engine_cb -- generated by attractor_pipeline.py
# Script CHOP onCook == once per cook. Never make this a CHOP Execute
# onValueChange: that fires once per FFT bin and refreezes the cook.
import sys
SCRIPTS = "%s"
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)


def onCook(scriptOp):
    """Delegate to the tested engine rather than inline it here."""
    try:
        import attractor_engine
    except Exception as e:
        print("[attractor] engine import failed:", e)
        scriptOp.clear()
        for nm in ("tx", "ty", "tz", "fade"):
            scriptOp.appendChan(nm).vals = [0.0]
        return
    attractor_engine.cook(scriptOp)
    return
''' % SCRIPTS_DIR


# =============================================================================
# OPTIONAL GPU PATH -- not installed, not wired, not required
#
# The Python engine above is the shipped path and it is bounded at 16 k points.
# If you want 250 k, the state has to live in a texture. This is that shader:
# one texel per particle, RGBA32Float, position in .xyz, and a Feedback TOP
# ping-ponging the previous frame into input 0.
#
# It is here as SOURCE, not as a built node, on purpose. GLSL compile failures
# are this project's single most expensive class of bug (the yellow-triangle
# afternoon), and a shader that has never been compiled on Thomas's GPU is a
# claim, not a feature. Wiring notes are in the runbook; verify it on a spare
# .toe before it goes anywhere near a show.
#
# Uniform slots follow the repo's hard-won convention: 0-INDEXED `uniname0` /
# `value0x`, not 1-indexed `uniformname1`.
# =============================================================================

ATTRACTOR_GLSL_COMPUTE = '''// attr_glsl_step -- one RK4 step of the blended attractor field, per texel.
// Input 0: previous positions (RGBA32Float; xyz = normalised position).
// Uniforms, 0-indexed slots:
//   0 uStep   (float)  seconds * speed for this frame
//   1 uMorph  (float)  cyclic morph position
//   2 uChaos  (float)  normalised 0..1
out vec4 fragColor;

uniform float uStep;
uniform float uMorph;
uniform float uChaos;

const float ESCAPE = 4.0;

float lerp1(float lo, float hi, float t) { return mix(lo, hi, clamp(t, 0.0, 1.0)); }

vec3 lorenzWorld(vec3 p, float chaos) {
    float rho = lerp1(26.0, 60.0, chaos);
    return vec3(10.0 * (p.y - p.x),
                p.x * (rho - p.z) - p.y,
                p.x * p.y - (8.0 / 3.0) * p.z);
}

vec3 thomasWorld(vec3 p, float chaos) {
    float b = lerp1(0.21, 0.10, chaos);
    return vec3(sin(p.y) - b * p.x,
                sin(p.z) - b * p.y,
                sin(p.x) - b * p.z);
}

vec3 aizawaWorld(vec3 p, float chaos) {
    float a = lerp1(0.94, 1.06, chaos);
    return vec3((p.z - 0.7) * p.x - 3.5 * p.y,
                3.5 * p.x + (p.z - 0.7) * p.y,
                0.6 + a * p.z - (p.z * p.z * p.z) / 3.0
                    - (p.x * p.x + p.y * p.y) * (1.0 + 0.25 * p.z)
                    + 0.1 * p.z * (p.x * p.x * p.x));
}

// Normalised field for system i: world = center + u * scale, then
// du/dt = f_world / scale * timeScale. Same frame as attractor_math.py.
vec3 fieldFor(int i, vec3 u, float chaos) {
    if (i == 0) {
        vec3 w = vec3(0.0, 0.0, 25.0) + u * 20.0;
        return lorenzWorld(w, chaos) * (0.60 / 20.0);
    } else if (i == 1) {
        vec3 w = u * 4.0;
        return thomasWorld(w, chaos) * (5.00 / 4.0);
    }
    vec3 w = vec3(0.0, 0.0, 0.85) + u * 1.5;
    return aizawaWorld(w, chaos) * (1.50 / 1.5);
}

vec3 field(vec3 u, float morph, float chaos) {
    float pos = mod(morph, 3.0);
    int a = int(floor(pos));
    int b = int(mod(float(a) + 1.0, 3.0));
    float w = pos - float(a);
    return mix(fieldFor(a, u, chaos), fieldFor(b, u, chaos), w);
}

void main() {
    vec3 u = texture(sTD2DInputs[0], vUV.st).xyz;
    float h = uStep;
    vec3 k1 = field(u, uMorph, uChaos);
    vec3 k2 = field(u + k1 * (h * 0.5), uMorph, uChaos);
    vec3 k3 = field(u + k2 * (h * 0.5), uMorph, uChaos);
    vec3 k4 = field(u + k3 * h, uMorph, uChaos);
    vec3 n = u + (h / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4);

    // The escape guard, GPU side. A texel that diverges is respawned from a
    // deterministic point derived from its own uv, so the fleet does not
    // collapse onto one seed after a bad frame.
    bool bad = any(isnan(n)) || any(isinf(n)) || any(greaterThan(abs(n), vec3(ESCAPE)));
    if (bad) {
        n = vec3(0.05, 0.05, -0.20) + (vec3(vUV.s, vUV.t, vUV.s * vUV.t) - 0.5) * 0.12;
    }
    fragColor = TDOutputSwizzle(vec4(n, 1.0));
}
'''
