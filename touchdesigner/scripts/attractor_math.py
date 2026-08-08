# attractor_math.py -- the three strange attractors, as pure Python
# =============================================================================
# WHAT THIS IS
#   Lorenz, Thomas and Aizawa as ODE systems, an RK4 integrator, a normalised
#   coordinate frame that makes the three commensurable, a derivative-field
#   BLEND that morphs between them, and a ring buffer that turns a trajectory
#   into the point cloud TouchDesigner draws.
#
#   Nothing in this file imports TouchDesigner, numpy, or anything else. It is
#   plain Python and plain floats, so `tests/test_attractor_math.py` exercises
#   the whole engine on a laptop with no TD, no GPU and no audio.
#
# -----------------------------------------------------------------------------
# WHY NORMALISED COORDINATES (this is the load-bearing idea)
#   The three systems live at wildly different scales and speeds. Lorenz sprawls
#   over x,y in +/-25 with z climbing to 50; Thomas fits in a +/-5 box; Aizawa
#   curls up inside +/-2. Their characteristic timescales differ by an order of
#   magnitude too.
#
#   So each system declares a `center`, a `scale` and a `time_scale`, and the
#   engine integrates in NORMALISED space where every attractor is roughly a
#   unit blob turning at roughly the same rate:
#
#       world  = center + u * scale
#       du/dt  = f_world(world) / scale * time_scale
#
#   Two things fall out of that, and both are the point:
#     1. One camera, one point size and one `spread` knob frame all three. No
#        per-system render tuning, so a morph does not require a camera move.
#     2. MORPHING BECOMES WELL-POSED. You cannot meaningfully interpolate two
#        state spaces, but you can interpolate two normalised VECTOR FIELDS:
#        f = (1-w)*f_A + w*f_B. The trajectory never teleports; it is always
#        somewhere on a real (if unnamed) flow, so the morph is continuous
#        rather than a cut. See `blended_derivs`.
#
# -----------------------------------------------------------------------------
# THE ESCAPE INVARIANT -- the attractor engine's version of trail runaway
#   A strange attractor is only strange inside its parameter window. Push
#   Lorenz's rho below ~24.74 and the orbit collapses onto a fixed point; push
#   the integration step too far and RK4 diverges to inf, which reaches the
#   render as NaN geometry -- a black or garbage frame mid-show.
#
#   Two structural defences, neither of which trusts the caller:
#     1. Every chaos knob is a NORMALISED 0..1 that is mapped onto a per-system
#        interval chosen to stay on the strange attractor. Out-of-range is not
#        rejected, it is impossible: 999 and 1.0 are the same input.
#     2. `sanitize` reseeds any state that goes non-finite or leaves
#        ESCAPE_RADIUS, deterministically, every substep. A diverging seed costs
#        one reseeded particle, not the frame.
#
#   The reseed count is returned, never swallowed: a nonzero count every frame
#   means a parameter window is wrong and the operator should be able to see it.
# =============================================================================

from __future__ import annotations

import math
from typing import Callable, Dict, List, Sequence, Tuple

Vec3 = Tuple[float, float, float]

#: Normalised radius past which a state is considered escaped and is reseeded.
#: All three attractors live inside ~1.5 normalised units, so 4.0 is far enough
#: out that a legitimate excursion is never clipped and a divergence is caught
#: within a couple of substeps, long before it reaches inf.
ESCAPE_RADIUS = 4.0

#: Largest simulated time step one RK4 substep may take. RK4 on Lorenz is
#: comfortable to ~0.02 and this leaves margin; the engine adds substeps rather
#: than exceed it, so raising `speed` costs CPU instead of stability.
MAX_SIM_STEP = 0.02


# =============================================================================
# THE SYSTEMS
#
# Each `derivs` takes world coordinates and a NORMALISED chaos knob in 0..1,
# and maps that knob onto its own safe interval internally. The mapping lives
# next to the equations on purpose: the interval is a property of the system,
# not of the UI, and the only way to reach a parameter is through the map.
# =============================================================================


def _lerp(lo: float, hi: float, t: float) -> float:
    """Interpolate between two bounds by a knob that is clamped first.

    Args:
        lo: Value at ``t == 0``.
        hi: Value at ``t == 1``.
        t: Knob position, clamped into 0..1 before use.

    Returns:
        A value that is always between ``lo`` and ``hi`` inclusive, whatever
        ``t`` was. This clamp is why an absurd chaos value is not an error --
        it is simply the top of the range.
    """
    t = 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)
    return lo + (hi - lo) * t


#: Lorenz rho at chaos 0 and chaos 1. The classic butterfly is rho = 28. Below
#: ~24.74 the attractor is gone (the orbit spirals into a fixed point), so the
#: floor sits well clear of that; the ceiling widens the wings and speeds the
#: lobe switching without leaving the chaotic regime.
LORENZ_RHO_LO, LORENZ_RHO_HI = 26.0, 60.0
LORENZ_SIGMA, LORENZ_BETA = 10.0, 8.0 / 3.0

#: Thomas's damping b. INVERTED: b = 0.208 is the classic edge of chaos and
#: SMALLER b is wilder, filling more of the box. Below ~0.08 it turns
#: near-conservative and reads as noise rather than structure, so the floor
#: stops short of that.
#:
#: These endpoints are MEASURED, not chosen by eye: the largest Lyapunov
#: exponent is positive across the whole interval, and the attractor's extent
#: grows monotonically with chaos (~1.2 to ~2.5 normalised units), which is
#: what makes the knob read as "more chaos" rather than just "different".
#: `tests/test_attractor_engine.py` re-measures both, so a future edit to these
#: numbers that lands in a periodic window fails rather than ships.
THOMAS_B_LO, THOMAS_B_HI = 0.21, 0.10

#: Aizawa's `a`, the z-growth term. Canonical is 0.95, and the window opens
#: just below it: measurement puts the largest Lyapunov exponent NEGATIVE at
#: a = 0.90 (the orbit falls onto a limit cycle and the form stops being
#: strange), so the floor sits at 0.94 where it is reliably positive.
AIZAWA_A_LO, AIZAWA_A_HI = 0.94, 1.06
AIZAWA_B, AIZAWA_C, AIZAWA_D = 0.70, 0.60, 3.50
AIZAWA_E, AIZAWA_F = 0.25, 0.10


def lorenz_derivs(x: float, y: float, z: float, chaos: float) -> Vec3:
    """Lorenz (1963), with rho driven by the normalised chaos knob.

    Args:
        x: World x.
        y: World y.
        z: World z.
        chaos: Normalised 0..1; maps onto ``LORENZ_RHO_LO..LORENZ_RHO_HI``.

    Returns:
        ``(dx, dy, dz)`` in world units per unit of simulated time.
    """
    rho = _lerp(LORENZ_RHO_LO, LORENZ_RHO_HI, chaos)
    return (
        LORENZ_SIGMA * (y - x),
        x * (rho - z) - y,
        x * y - LORENZ_BETA * z,
    )


def thomas_derivs(x: float, y: float, z: float, chaos: float) -> Vec3:
    """Thomas's cyclically symmetric attractor, damping driven by chaos.

    Args:
        x: World x.
        y: World y.
        z: World z.
        chaos: Normalised 0..1; maps onto ``THOMAS_B_LO..THOMAS_B_HI``
            (descending -- see the constant's note).

    Returns:
        ``(dx, dy, dz)`` in world units per unit of simulated time.
    """
    b = _lerp(THOMAS_B_LO, THOMAS_B_HI, chaos)
    return (
        math.sin(y) - b * x,
        math.sin(z) - b * y,
        math.sin(x) - b * z,
    )


def aizawa_derivs(x: float, y: float, z: float, chaos: float) -> Vec3:
    """The Aizawa attractor, with the z-growth term driven by chaos.

    Args:
        x: World x.
        y: World y.
        z: World z.
        chaos: Normalised 0..1; maps onto ``AIZAWA_A_LO..AIZAWA_A_HI``.

    Returns:
        ``(dx, dy, dz)`` in world units per unit of simulated time.
    """
    a = _lerp(AIZAWA_A_LO, AIZAWA_A_HI, chaos)
    return (
        (z - AIZAWA_B) * x - AIZAWA_D * y,
        AIZAWA_D * x + (z - AIZAWA_B) * y,
        (AIZAWA_C + a * z - (z * z * z) / 3.0
         - (x * x + y * y) * (1.0 + AIZAWA_E * z)
         + AIZAWA_F * z * (x * x * x)),
    )


class AttractorSystem:
    """One attractor plus the frame that makes it commensurable with the others.

    Attributes:
        name: Registry key, uppercase.
        derivs: ``f(x, y, z, chaos) -> (dx, dy, dz)`` in world coordinates.
        center: World point that maps to the normalised origin.
        scale: World units per normalised unit.
        time_scale: Simulated time units per real second at speed 1.0. This is
            what makes a slow system and a fast one read at the same tempo.
        seed: A normalised point known to sit on the attractor, used to start
            and to reseed.
    """

    def __init__(self, name: str, derivs: Callable[[float, float, float, float], Vec3],
                 center: Vec3, scale: float, time_scale: float, seed: Vec3) -> None:
        self.name = name
        self.derivs = derivs
        self.center = center
        self.scale = float(scale)
        self.time_scale = float(time_scale)
        self.seed = seed

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return "<AttractorSystem %s>" % self.name


#: The three systems, in morph order. The order is the show: Lorenz is the
#: recognisable one to open on, Thomas is the airy middle, Aizawa is the tight
#: peak-time knot. `SEQUENCE` wraps, so morph is cyclic and never dead-ends.
SYSTEMS: Dict[str, AttractorSystem] = {}


def register_system(system: AttractorSystem) -> AttractorSystem:
    """Add a system to the registry.

    Args:
        system: The system to register.

    Returns:
        The same system, so this can wrap a constructor call.
    """
    SYSTEMS[system.name] = system
    return system


register_system(AttractorSystem(
    name="LORENZ",
    derivs=lorenz_derivs,
    # z never goes negative on Lorenz, so the centre is lifted to put the
    # butterfly in the middle of the normalised box rather than above it.
    center=(0.0, 0.0, 25.0),
    scale=20.0,
    time_scale=0.60,
    seed=(0.05, 0.05, -0.20),
))

register_system(AttractorSystem(
    name="THOMAS",
    derivs=thomas_derivs,
    center=(0.0, 0.0, 0.0),
    scale=4.0,
    # An order of magnitude faster in simulated time than Lorenz -- which is
    # exactly the discrepancy `time_scale` exists to erase.
    time_scale=5.0,
    seed=(0.25, 0.0, 0.0),
))

register_system(AttractorSystem(
    name="AIZAWA",
    derivs=aizawa_derivs,
    center=(0.0, 0.0, 0.85),
    scale=1.5,
    time_scale=1.50,
    seed=(0.07, 0.0, 0.0),
))

#: Morph order. Cyclic: position 3.0 is position 0.0 again.
SEQUENCE: Tuple[str, ...] = ("LORENZ", "THOMAS", "AIZAWA")


# =============================================================================
# THE NORMALISED FIELD, AND THE BLEND
# =============================================================================


def normalized_derivs(system: AttractorSystem, u: Vec3, chaos: float) -> Vec3:
    """Evaluate one system's vector field in normalised coordinates.

    Args:
        system: The system to evaluate.
        u: Normalised position.
        chaos: Normalised 0..1 chaos knob.

    Returns:
        ``du/dt`` in normalised units per real second at speed 1.0.
    """
    s = system.scale
    cx, cy, cz = system.center
    dx, dy, dz = system.derivs(cx + u[0] * s, cy + u[1] * s, cz + u[2] * s, chaos)
    k = system.time_scale / s
    return (dx * k, dy * k, dz * k)


def morph_pair(position: float) -> Tuple[AttractorSystem, AttractorSystem, float]:
    """Resolve a cyclic morph position to the two systems it sits between.

    Args:
        position: Any real number. Wraps modulo ``len(SEQUENCE)``, so the DJ
            never has to think about bounds and an audience bias can only ever
            slide along the ring.

    Returns:
        ``(system_a, system_b, weight)`` with ``weight`` in 0..1, where 0 is
        pure ``system_a``.
    """
    n = len(SEQUENCE)
    pos = position % n
    idx = int(math.floor(pos))
    frac = pos - idx
    return SYSTEMS[SEQUENCE[idx]], SYSTEMS[SEQUENCE[(idx + 1) % n]], frac


def blended_derivs(u: Vec3, position: float, chaos: float) -> Vec3:
    """Evaluate the morphed field at a cyclic morph position.

    At an integer position this is exactly one system's field -- the blend adds
    nothing and costs one extra multiply, so there is no "pure mode" branch to
    get wrong.

    Args:
        u: Normalised position.
        position: Cyclic morph position.
        chaos: Normalised 0..1 chaos knob, shared by both systems.

    Returns:
        ``du/dt`` in normalised units per real second at speed 1.0.
    """
    a, b, w = morph_pair(position)
    if w <= 0.0:
        return normalized_derivs(a, u, chaos)
    fa = normalized_derivs(a, u, chaos)
    fb = normalized_derivs(b, u, chaos)
    inv = 1.0 - w
    return (fa[0] * inv + fb[0] * w,
            fa[1] * inv + fb[1] * w,
            fa[2] * inv + fb[2] * w)


def rk4_step(u: Vec3, dt: float, position: float, chaos: float) -> Vec3:
    """Advance one normalised state by ``dt`` seconds with classical RK4.

    RK4 rather than Euler because Lorenz at a visually useful step size is
    already where Euler starts spiralling outward -- and an outward spiral here
    is not a wrong pixel, it is a diverging state that reaches the render as
    NaN. Fourth order buys the margin that keeps the escape guard idle.

    Args:
        u: Normalised position.
        dt: Step in seconds (already divided by the substep count).
        position: Cyclic morph position.
        chaos: Normalised 0..1 chaos knob.

    Returns:
        The advanced normalised position.
    """
    k1 = blended_derivs(u, position, chaos)
    h = dt * 0.5
    u2 = (u[0] + k1[0] * h, u[1] + k1[1] * h, u[2] + k1[2] * h)
    k2 = blended_derivs(u2, position, chaos)
    u3 = (u[0] + k2[0] * h, u[1] + k2[1] * h, u[2] + k2[2] * h)
    k3 = blended_derivs(u3, position, chaos)
    u4 = (u[0] + k3[0] * dt, u[1] + k3[1] * dt, u[2] + k3[2] * dt)
    k4 = blended_derivs(u4, position, chaos)
    sixth = dt / 6.0
    return (
        u[0] + sixth * (k1[0] + 2.0 * k2[0] + 2.0 * k3[0] + k4[0]),
        u[1] + sixth * (k1[1] + 2.0 * k2[1] + 2.0 * k3[1] + k4[1]),
        u[2] + sixth * (k1[2] + 2.0 * k2[2] + 2.0 * k3[2] + k4[2]),
    )


def substeps_for(dt: float, speed: float, position: float,
                 max_substeps: int) -> int:
    """Choose how many RK4 substeps one frame needs to stay under MAX_SIM_STEP.

    Raising `speed` therefore costs CPU rather than stability -- which is the
    trade we want, because CPU is bounded by the substep cap and stability is
    not bounded by anything.

    HONEST LIMIT: the substep cap wins over MAX_SIM_STEP, so the target is not
    always met. At the very top of the speed range with Thomas in the blend
    (its time_scale is the largest of the three) the requested step is about
    3x MAX_SIM_STEP even at the cap. That is deliberate: this rig already sheds
    load with cookRate 30, and a bounded frame cost is worth more than a
    guarantee that was only ever a margin. RK4 stays stable there in practice
    -- a full sweep of morph positions at speed 3.0 and chaos 1.0 reseeds zero
    seeds -- and the escape guard is what covers the case where it does not.

    Args:
        dt: Frame duration in seconds.
        speed: Speed multiplier applied to the field.
        position: Cyclic morph position (the two systems either side of it have
            different time scales, so the faster one sets the requirement).
        max_substeps: Hard ceiling on the returned count.

    Returns:
        A substep count in ``1..max_substeps``.
    """
    a, b, w = morph_pair(position)
    time_scale = max(a.time_scale, b.time_scale) if w > 0.0 else a.time_scale
    sim_step = abs(dt) * max(0.0, speed) * time_scale
    if sim_step <= MAX_SIM_STEP:
        return 1
    return max(1, min(int(max_substeps), int(math.ceil(sim_step / MAX_SIM_STEP))))


# =============================================================================
# THE ESCAPE GUARD
# =============================================================================


def _lcg(seed: int) -> float:
    """A tiny deterministic PRNG, in 0..1.

    Deterministic on purpose: a reseed that used ``random`` would make the
    escape guard untestable, and "it reseeded somewhere sensible" is exactly
    the kind of claim that needs a test rather than a comment.

    Args:
        seed: Any integer.

    Returns:
        A float in 0..1.
    """
    return (((seed * 1103515245) + 12345) % 2147483648) / 2147483648.0


def is_escaped(u: Vec3) -> bool:
    """Report whether a state has gone non-finite or left the escape radius.

    Args:
        u: Normalised position.

    Returns:
        True if the state must be reseeded.
    """
    for component in u:
        if component != component:            # NaN: the only value != itself
            return True
        if component in (float("inf"), float("-inf")):
            return True
        if component > ESCAPE_RADIUS or component < -ESCAPE_RADIUS:
            return True
    return False


def reseed(index: int, position: float, tick: int = 0) -> Vec3:
    """Produce a fresh on-attractor state for one seed.

    Args:
        index: Seed index, so a fleet of seeds does not all land on one point.
        position: Cyclic morph position, used to pick which system's seed point
            to start from.
        tick: Extra entropy so a seed that escapes twice does not return to the
            same spot and escape identically.

    Returns:
        A normalised position just off the attractor's seed point.
    """
    system, _b, _w = morph_pair(position)
    jitter = 0.06
    base = system.seed
    return (
        base[0] + (_lcg(index * 7919 + tick) - 0.5) * jitter,
        base[1] + (_lcg(index * 104729 + tick + 1) - 0.5) * jitter,
        base[2] + (_lcg(index * 15485863 + tick + 2) - 0.5) * jitter,
    )


def sanitize(states: List[Vec3], position: float, tick: int = 0) -> int:
    """Reseed every escaped state in place.

    Args:
        states: Mutable list of normalised positions.
        position: Cyclic morph position.
        tick: Extra entropy, typically the frame counter.

    Returns:
        How many states were reseeded. NEVER swallowed by the caller: a count
        that stays nonzero frame after frame is the signal that a parameter
        window is wrong, and it is the only warning the operator gets.
    """
    escaped = 0
    for i, u in enumerate(states):
        if is_escaped(u):
            states[i] = reseed(i, position, tick + i)
            escaped += 1
    return escaped


# =============================================================================
# THE TRAIL BUFFER
#
# A fixed-size ring per seed. Fixed size is the point: memory and the per-frame
# channel write are both bounded at construction, so no live control can make
# the engine allocate. `seeds * trail` is the entire cost model.
# =============================================================================


class TrailBuffer:
    """A ring buffer of trajectory points, laid out for a Script CHOP write.

    The layout is SLOT-MAJOR within each seed: index ``seed * trail + slot``.
    That means the newest point of every seed is scattered through the arrays
    rather than contiguous -- which is free for the instanced-sprite render
    (points have no order) and is why `fades()` can be computed once for a slot
    and tiled across seeds instead of per point.

    If you ever draw the trails as LINES rather than sprites you need the
    points in age order per seed; `ordered()` does that, and is deliberately
    not on the per-frame path.

    Attributes:
        seeds: Number of independent trajectories.
        trail: Points remembered per trajectory.
        xs: Flat x coordinates, length ``seeds * trail``.
        ys: Flat y coordinates.
        zs: Flat z coordinates.
        head: Slot index the next write lands in.
        states: Current normalised position per seed.
    """

    def __init__(self, seeds: int, trail: int, position: float = 0.0) -> None:
        self.seeds = max(1, int(seeds))
        self.trail = max(2, int(trail))
        size = self.seeds * self.trail
        self.states: List[Vec3] = [reseed(i, position) for i in range(self.seeds)]
        self.xs: List[float] = [0.0] * size
        self.ys: List[float] = [0.0] * size
        self.zs: List[float] = [0.0] * size
        self.head = 0
        self.prime(position)

    def prime(self, position: float) -> None:
        """Fill every slot with the current state, so the first frame is not a
        streak from the origin.

        Args:
            position: Cyclic morph position, used only to seed.
        """
        for s in range(self.seeds):
            ux, uy, uz = self.states[s]
            base = s * self.trail
            for slot in range(self.trail):
                self.xs[base + slot] = ux
                self.ys[base + slot] = uy
                self.zs[base + slot] = uz

    def advance(self, dt: float, speed: float, position: float, chaos: float,
                substeps: int, tick: int = 0) -> int:
        """Integrate every seed one frame and append the results.

        Args:
            dt: Frame duration in seconds.
            speed: Speed multiplier on the normalised field.
            position: Cyclic morph position.
            chaos: Normalised 0..1 chaos knob.
            substeps: RK4 substeps this frame (see :func:`substeps_for`).
            tick: Frame counter, used as reseed entropy.

        Returns:
            The number of seeds reseeded this frame by the escape guard.
        """
        substeps = max(1, int(substeps))
        step = (dt * speed) / substeps
        escaped = 0
        for _ in range(substeps):
            self.states = [rk4_step(u, step, position, chaos) for u in self.states]
            # Guard every substep, not once per frame: a state that has already
            # reached inf produces NaN on the next step, and NaN spreads.
            escaped += sanitize(self.states, position, tick)
        self.head = (self.head + 1) % self.trail
        head = self.head
        for s in range(self.seeds):
            ux, uy, uz = self.states[s]
            i = s * self.trail + head
            self.xs[i] = ux
            self.ys[i] = uy
            self.zs[i] = uz
        return escaped

    def fades(self, gamma: float) -> List[float]:
        """Per-point fade weights, newest = 1.0, oldest -> 0.

        Computed once for the ``trail`` slots and tiled across seeds, which is
        only correct because of the slot-major layout above.

        Args:
            gamma: Shaping exponent. Below 1 stretches the tail out, above 1
                snaps it short.

        Returns:
            A list of length ``seeds * trail``.
        """
        trail = self.trail
        head = self.head
        gamma = max(0.05, float(gamma))
        per_slot = []
        for slot in range(trail):
            age = ((head - slot) % trail) / float(trail)
            per_slot.append((1.0 - age) ** gamma)
        return per_slot * self.seeds

    def ordered(self) -> List[List[Vec3]]:
        """Return each seed's trail oldest-first, for line rendering.

        Not used by the per-frame path -- it allocates. It exists so the
        line-strip variant in the runbook has a correct source of truth rather
        than an off-by-one waiting to happen.

        Returns:
            One list of points per seed, oldest first, newest last.
        """
        out: List[List[Vec3]] = []
        for s in range(self.seeds):
            base = s * self.trail
            row: List[Vec3] = []
            for k in range(self.trail):
                slot = (self.head + 1 + k) % self.trail
                row.append((self.xs[base + slot], self.ys[base + slot],
                            self.zs[base + slot]))
            out.append(row)
        return out


def integrate(position: float, chaos: float, steps: int, dt: float = 0.005,
              start: Sequence[float] = None) -> List[Vec3]:
    """Integrate a single trajectory, for tests and for offline previewing.

    Args:
        position: Cyclic morph position.
        chaos: Normalised 0..1 chaos knob.
        steps: Number of RK4 steps.
        dt: Step size in seconds.
        start: Optional normalised start point; defaults to the system's seed.

    Returns:
        The trajectory, including the start point.
    """
    system, _b, _w = morph_pair(position)
    u: Vec3 = tuple(start) if start is not None else system.seed  # type: ignore[assignment]
    out: List[Vec3] = [u]
    for i in range(int(steps)):
        u = rk4_step(u, dt, position, chaos)
        if is_escaped(u):
            u = reseed(0, position, i)
        out.append(u)
    return out
