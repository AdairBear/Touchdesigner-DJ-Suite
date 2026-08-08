"""Offline tests for the chaotic-attractor engine.

Three things are asserted here, and they are the three that would cost a show:

  1. THE MATH IS ACTUALLY CHAOTIC AND ACTUALLY BOUNDED. Each system is
     integrated for thousands of steps and checked for the two properties that
     make it worth rendering -- it stays inside its box, and it does not settle
     onto a fixed point or a cycle. A "Lorenz" that has quietly collapsed to a
     dot is a bug you find on stage.
  2. THE CAPS HOLD FOR ANY INPUT. Every expression builder is EVALUATED against
     a fake ``op()`` world driven to absurd values -- a regex can be fooled by a
     rearranged expression, an evaluation cannot. This mirrors
     ``test_audience_osc.py`` deliberately: the attractor's clamps are the same
     clamps, applied to new knobs.
  3. THE AUDIENCE CANNOT BREACH THEM OR PICK A FORM. The chaos knob's whole
     range is already the safe parameter window, and the morph bias is smaller
     than one form. Both are asserted, not argued.

Run:  python3 -m pytest tests/test_attractor_engine.py -v
"""

import math
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "touchdesigner" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import attractor_engine as ae  # noqa: E402
import attractor_math as am  # noqa: E402
import audience_control as aud  # noqa: E402
import dj_graphics_profiles as gp  # noqa: E402
import osc_profile_control as ctl  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent.parent / "python"))
from chat_bridge import config  # noqa: E402

#: Values a hostile or broken bridge might write. Same list as the audience
#: tests use, for the same reason: the clamp has to hold for all of them.
ABSURD = [0.0, 1.0, -1.0, 5.0, -5.0, 999.0, -999.0, 1e9, -1e9]

ATTRACTOR_PROFILES = [p for p in gp.PROFILES.values() if p.attractor is not None]
ATTRACTOR_IDS = [p.name for p in ATTRACTOR_PROFILES]
SPECS = [p.attractor for p in ATTRACTOR_PROFILES]


# ---------------------------------------------------------------------------
# Fake TD world, matching the one in test_dj_graphics_profiles.py.
# ---------------------------------------------------------------------------
class FakeChan:
    """A CHOP channel that reports a fixed value and behaves like a float."""

    def __init__(self, value):
        self._value = float(value)

    def eval(self):
        return self._value

    def __float__(self):
        return self._value

    def __mul__(self, other):
        return self._value * other

    __rmul__ = __mul__

    def __add__(self, other):
        return self._value + other

    __radd__ = __add__

    def __sub__(self, other):
        return self._value - other

    def __rsub__(self, other):
        return other - self._value

    def __truediv__(self, other):
        return self._value / other

    def __neg__(self):
        return -self._value

    def __lt__(self, other):
        return self._value < float(other)

    def __le__(self, other):
        return self._value <= float(other)

    def __gt__(self, other):
        return self._value > float(other)

    def __ge__(self, other):
        return self._value >= float(other)

    def __eq__(self, other):
        try:
            return self._value == float(other)
        except (TypeError, ValueError):
            return NotImplemented

    def __hash__(self):
        return hash(self._value)


class FakeCHOP:
    """A CHOP whose channels are addressable by name or index."""

    def __init__(self, by_name):
        self._by_name = {k: FakeChan(v) for k, v in by_name.items()}
        self._by_index = list(self._by_name.values())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._by_index[key]
        return self._by_name[key]


class FakeAbsTime:
    seconds = 1000.0
    frame = 60000


def make_op(kick=1.0, snare=1.0, energy=1.5, dj=0.0, audience=0.0):
    """Build a fake ``op()`` resolving every CHOP the attractor reads.

    Defaults are worst case: envelopes pinned on and the energy accumulator at
    the top of its 0.6..1.5 range.

    Args:
        kick: fx_kick_env['bass'].
        snare: fx_snare_env['high'].
        energy: fx_master['bass'].
        dj: Written to EVERY attr_dj channel at once.
        audience: Written to EVERY fx_audience channel at once.

    Returns:
        A callable suitable for injection as the TD ``op`` global.
    """
    channels = {name: audience for name in gp.AUDIENCE_CHANNELS}
    channels.update({name: 0.0 for name in gp.AUDIENCE_PULSE_CHANNELS})
    world = {
        "fx_kick_env": FakeCHOP({"bass": kick}),
        "fx_snare_env": FakeCHOP({"high": snare}),
        "fx_master": FakeCHOP({"bass": energy}),
        "fx_palette_engine": FakeCHOP({"primaryR": 0.5, "primaryG": 0.5,
                                       "primaryB": 0.5}),
        # An attractor profile is still a full profile, so its plan carries the
        # silhouette chain's expressions too.
        "fx_lfo_decay": FakeCHOP({"chan1": 0.0}),
        "fx_noise": FakeCHOP({"chan1": 1.0, "chan2": 1.0}),
        ae.DJ_CHOP: FakeCHOP({name: dj for name in ae.DJ_CHANNELS}),
        ae.AUDIENCE_CHOP: FakeCHOP(channels),
    }
    return lambda path: world.get(path)


def eval_expr(expr, **kwargs):
    """Evaluate a TD parameter expression against the fake world.

    On the deliberate ``eval``: every string comes from this repo's own
    builders, and standing them up the way TD would is the whole point. The
    namespace carries no builtins and only the handful of names TD exposes.

    Args:
        expr: The expression string as emitted by a builder.
        **kwargs: Forwarded to ``make_op``.

    Returns:
        The numeric result.
    """
    namespace = {
        "__builtins__": {},
        "op": make_op(**kwargs),
        "absTime": FakeAbsTime,
        "min": min,
        "max": max,
        "int": int,
        "abs": abs,
    }
    return eval(expr, namespace)  # noqa: S307 - self-generated input


# ---------------------------------------------------------------------------
# Measurements the math tests are built on.
# ---------------------------------------------------------------------------
def lyapunov(position, chaos, steps=12000, dt=0.001, settle=3000):
    """Estimate the largest Lyapunov exponent by renormalisation.

    Two trajectories are held a fixed tiny distance apart: each step the
    separation is measured, its logarithm accumulated, and the perturbed point
    pulled back onto the original separation. That keeps the estimate in the
    linear regime instead of letting it saturate at the attractor's diameter,
    which is what makes it a measurement rather than a coin flip.

    Args:
        position: Cyclic morph position.
        chaos: Normalised 0..1 chaos knob.
        steps: Steps to average over.
        dt: Step size in seconds.
        settle: Steps to run first, so the estimate is taken ON the attractor
            rather than on the transient falling toward it. Without this, a
            limit cycle reads as chaotic for its first few hundred steps.

    Returns:
        The exponent per second. Positive means sensitive dependence.
    """
    system, _b, _w = am.morph_pair(position)
    u = system.seed
    for _ in range(settle):
        u = am.rk4_step(u, dt, position, chaos)
    offset = 1e-8
    v = (u[0] + offset, u[1], u[2])
    total = 0.0
    for _ in range(steps):
        u = am.rk4_step(u, dt, position, chaos)
        v = am.rk4_step(v, dt, position, chaos)
        separation = math.dist(u, v)
        if separation <= 0.0:
            continue
        total += math.log(separation / offset)
        pull = offset / separation
        v = (u[0] + (v[0] - u[0]) * pull,
             u[1] + (v[1] - u[1]) * pull,
             u[2] + (v[2] - u[2]) * pull)
    return total / (steps * dt)


def extent(position, chaos, steps=8000, dt=0.004):
    """Measure how much space the settled trajectory occupies.

    Args:
        position: Cyclic morph position.
        chaos: Normalised 0..1 chaos knob.
        steps: Steps to integrate.
        dt: Step size in seconds.

    Returns:
        The largest per-axis range over the second half of the run, in
        normalised units.
    """
    tail = am.integrate(position, chaos, steps=steps, dt=dt)[steps // 2:]
    return max(max(u[axis] for u in tail) - min(u[axis] for u in tail)
               for axis in range(3))


# ===========================================================================
# 1. THE MATH
# ===========================================================================
class TestTheAttractorsAreAttractors:
    """Bounded and non-degenerate -- the two properties that make it a look."""

    @pytest.mark.parametrize("name", am.SEQUENCE)
    @pytest.mark.parametrize("chaos", [0.0, 0.5, 1.0])
    def test_the_trajectory_stays_inside_the_escape_radius(self, name, chaos):
        """A diverging system reaches the render as NaN geometry: a black frame."""
        position = float(am.SEQUENCE.index(name))
        traj = am.integrate(position, chaos, steps=6000, dt=0.005)
        for u in traj:
            assert not am.is_escaped(u), "%s escaped at chaos=%.1f" % (name, chaos)

    @pytest.mark.parametrize("name", am.SEQUENCE)
    @pytest.mark.parametrize("chaos", [0.0, 0.5, 1.0])
    def test_the_trajectory_does_not_collapse_to_a_point(self, name, chaos):
        """Lorenz below rho ~24.74 is a dot. The parameter windows exist to
        keep every system clear of its own version of that, and the tail of a
        long run is where a collapse actually shows up."""
        position = float(am.SEQUENCE.index(name))
        traj = am.integrate(position, chaos, steps=8000, dt=0.005)
        tail = traj[4000:]
        for axis in range(3):
            values = [u[axis] for u in tail]
            if max(values) - min(values) > 0.05:
                return
        pytest.fail("%s collapsed at chaos=%.1f -- no axis moves" % (name, chaos))

    @pytest.mark.parametrize("name", am.SEQUENCE)
    @pytest.mark.parametrize("chaos", [0.0, 1.0])
    def test_both_ends_of_every_window_are_chaotic(self, name, chaos):
        """Sensitive dependence at the extremes of what any control can ask for.

        Measured with a RENORMALISING estimator rather than by integrating two
        nearby starts and comparing endpoints. On a bounded attractor two
        diverged points can be close again by coincidence, so an endpoint
        comparison is a coin flip dressed as a measurement -- and it is exactly
        how the first draft of these windows passed while Thomas sat in its
        periodic band above b = 0.208.

        The ends are what the caps guarantee: a fully driven chaos nudge, or a
        fully negative one, still lands on a strange attractor.
        """
        position = float(am.SEQUENCE.index(name))
        assert lyapunov(position, chaos) > 0.0, (
            "%s at chaos=%.1f is not chaotic -- the parameter window has "
            "drifted into a periodic band" % (name, chaos))

    @pytest.mark.parametrize("name", am.SEQUENCE)
    def test_most_of_every_window_is_chaotic(self, name):
        """The interior, stated as what is actually true.

        Periodic windows are dense in these families -- Thomas has a narrow one
        around b = 0.155, mid-range on its knob. Asserting chaos at every
        sampled point would be asserting something false about the mathematics,
        and a test that demands a false thing gets deleted the first time it
        fails honestly.

        So: the overwhelming majority must be chaotic, and the neighbours of
        any periodic point must not be. A form that briefly settles onto a
        cycle reads as a winding orbit, not as a freeze -- and chaos is
        modulated by the track anyway, so it never sits on one value.
        """
        position = float(am.SEQUENCE.index(name))
        exponents = [lyapunov(position, c / 8.0) for c in range(9)]
        chaotic = sum(1 for e in exponents if e > 0.0)
        assert chaotic >= 7, "%s is chaotic at only %d/9 of its window: %s" % (
            name, chaotic, ["%+.3f" % e for e in exponents])

    @pytest.mark.parametrize("name", am.SEQUENCE)
    def test_more_chaos_opens_the_form_up(self, name):
        """The knob has to READ as more chaos, not merely be different.

        Extent is the visible proxy: the form should occupy more of the frame
        at the top of the window than at the bottom.
        """
        position = float(am.SEQUENCE.index(name))
        assert extent(position, 1.0) > extent(position, 0.0)

    @pytest.mark.parametrize("position", [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 2.99])
    def test_every_blend_is_bounded_too(self, position):
        """The morph passes through fields that are not any named system.

        Their boundedness is not inherited from the endpoints, so it is
        measured rather than assumed -- this test is why the escape guard is a
        backstop instead of the primary defence.

        Note what is NOT claimed: an intermediate field is not asserted to be
        chaotic. Measurement says several of them are not -- a half-Lorenz,
        half-Thomas flow settles onto a cycle. That is fine and it is visible:
        a morph passes through those states over seconds, and a briefly
        periodic form reads as the shape resolving, not as a freeze. What the
        show cannot survive is an UNBOUNDED one, and that is what this checks.
        """
        traj = am.integrate(position, 0.6, steps=4000, dt=0.005)
        for u in traj:
            assert not am.is_escaped(u)

    def test_morph_is_cyclic_and_never_indexes_out_of_range(self):
        for position in (-10.5, -1.0, 0.0, 2.999, 3.0, 3.5, 1e6):
            a, b, w = am.morph_pair(position)
            assert a.name in am.SYSTEMS and b.name in am.SYSTEMS
            assert 0.0 <= w < 1.0

    def test_an_integer_position_is_exactly_one_system(self):
        for index, name in enumerate(am.SEQUENCE):
            u = (0.3, -0.2, 0.4)
            blended = am.blended_derivs(u, float(index), 0.5)
            direct = am.normalized_derivs(am.SYSTEMS[name], u, 0.5)
            assert blended == pytest.approx(direct)

    def test_the_chaos_knob_is_saturating_not_wrapping(self):
        """999 and 1.0 must be the same input -- that IS the cap."""
        u = (0.3, -0.2, 0.4)
        top = am.blended_derivs(u, 0.0, 1.0)
        assert am.blended_derivs(u, 0.0, 999.0) == pytest.approx(top)
        bottom = am.blended_derivs(u, 0.0, 0.0)
        assert am.blended_derivs(u, 0.0, -999.0) == pytest.approx(bottom)

    def test_chaos_actually_changes_the_field(self):
        """A clamp that clamps to a no-op is not safety, it is a dead knob."""
        u = (0.4, 0.3, 0.2)
        assert am.blended_derivs(u, 0.0, 0.0) != am.blended_derivs(u, 0.0, 1.0)


class TestTheEscapeGuard:
    def test_a_diverged_state_is_reseeded_onto_the_attractor(self):
        states = [(1e30, 0.0, 0.0), (0.1, 0.1, 0.1), (float("nan"), 0.0, 0.0)]
        count = am.sanitize(states, 0.0, tick=3)
        assert count == 2
        assert states[1] == (0.1, 0.1, 0.1), "a healthy state must not be touched"
        for u in states:
            assert not am.is_escaped(u)

    def test_reseeding_is_deterministic(self):
        """Otherwise the guard is untestable, and an untested guard is a story."""
        assert am.reseed(4, 1.0, 9) == am.reseed(4, 1.0, 9)

    def test_two_seeds_do_not_land_on_the_same_point(self):
        assert am.reseed(1, 0.0, 0) != am.reseed(2, 0.0, 0)

    def test_infinities_and_nans_are_all_caught(self):
        for bad in (float("inf"), float("-inf"), float("nan"), 1e12, -1e12):
            assert am.is_escaped((bad, 0.0, 0.0))
            assert am.is_escaped((0.0, bad, 0.0))
            assert am.is_escaped((0.0, 0.0, bad))


class TestTheTrailBuffer:
    def test_the_buffer_size_is_fixed_at_construction(self):
        buf = am.TrailBuffer(8, 32)
        for tick in range(200):
            buf.advance(1 / 30.0, 1.0, 0.0, 0.4, substeps=2, tick=tick)
        assert len(buf.xs) == 8 * 32
        assert len(buf.ys) == 8 * 32
        assert len(buf.zs) == 8 * 32

    def test_every_emitted_point_is_finite_after_a_long_run(self):
        buf = am.TrailBuffer(6, 24)
        for tick in range(500):
            buf.advance(1 / 30.0, 3.0, tick * 0.01, 1.0, substeps=4, tick=tick)
        for series in (buf.xs, buf.ys, buf.zs):
            for value in series:
                assert value == value
                assert abs(value) <= am.ESCAPE_RADIUS

    def test_fades_run_from_newest_to_oldest_and_stay_in_range(self):
        buf = am.TrailBuffer(3, 16)
        buf.advance(1 / 30.0, 1.0, 0.0, 0.5, substeps=1, tick=1)
        fades = buf.fades(1.0)
        assert len(fades) == 3 * 16
        assert all(0.0 <= f <= 1.0 for f in fades)
        assert fades[buf.head] == pytest.approx(1.0)

    def test_ordered_returns_each_trail_oldest_first(self):
        buf = am.TrailBuffer(2, 8)
        for tick in range(20):
            buf.advance(1 / 30.0, 1.0, 0.0, 0.5, substeps=1, tick=tick)
        rows = buf.ordered()
        assert len(rows) == 2 and all(len(r) == 8 for r in rows)
        # The last entry of each row must be the seed's current state.
        for seed, row in enumerate(rows):
            assert row[-1] == pytest.approx(buf.states[seed])

    def test_substeps_rise_with_speed_and_stop_at_the_cap(self):
        slow = am.substeps_for(1 / 30.0, 0.5, 0.0, ae.ATTRACTOR_MAX_SUBSTEPS)
        fast = am.substeps_for(1 / 30.0, 3.0, 1.0, ae.ATTRACTOR_MAX_SUBSTEPS)
        assert slow <= fast <= ae.ATTRACTOR_MAX_SUBSTEPS
        absurd = am.substeps_for(1.0, 1e6, 1.0, ae.ATTRACTOR_MAX_SUBSTEPS)
        assert absurd == ae.ATTRACTOR_MAX_SUBSTEPS


# ===========================================================================
# 2. THE COST CEILING
# ===========================================================================
class TestTheWorkPerCookIsBounded:
    def test_the_point_count_can_never_exceed_the_product_cap(self):
        for seeds, trail in ((1, 1), (10_000, 10_000), (64, 512), (3, 999)):
            n_seeds, n_trail = ae.resolve_counts(seeds, trail)
            assert n_seeds * n_trail <= ae.ATTRACTOR_MAX_POINTS
            assert 1 <= n_seeds <= ae.ATTRACTOR_MAX_SEEDS
            assert 2 <= n_trail <= ae.ATTRACTOR_MAX_TRAIL

    def test_garbage_counts_do_not_raise(self):
        """These arrive from a CHOP read, so they can be anything at all."""
        for bad in (None, "eight", float("nan"), float("inf"), -5):
            seeds, trail = ae.resolve_counts(bad, bad)
            assert seeds >= 1 and trail >= 2

    @pytest.mark.parametrize("spec", SPECS, ids=ATTRACTOR_IDS)
    def test_every_shipped_spec_is_already_within_the_caps(self, spec):
        """A spec that would be clamped is a profile that lies about itself."""
        assert ae.resolve_counts(spec.seeds, spec.trail) == (spec.seeds, spec.trail)

    @pytest.mark.parametrize("spec", SPECS, ids=ATTRACTOR_IDS)
    def test_every_shipped_spec_validates(self, spec):
        assert ae.validate_spec(spec) == []

    @pytest.mark.parametrize("profile", ATTRACTOR_PROFILES, ids=ATTRACTOR_IDS)
    def test_every_attractor_profile_passes_the_palette_guard(self, profile):
        assert gp.validate_profile(profile) == []


# ===========================================================================
# 3. THE CLAMPS, EVALUATED
# ===========================================================================
class TestChaosIsStructurallyCapped:
    @pytest.mark.parametrize("spec", SPECS, ids=ATTRACTOR_IDS)
    @pytest.mark.parametrize("value", ABSURD)
    def test_chaos_stays_in_0_1_at_any_audience_value(self, spec, value):
        result = eval_expr(ae.chaos_expr(spec, audience=True),
                           kick=1.0, energy=1.5, dj=1.0, audience=value)
        assert 0.0 <= result <= ae.ATTRACTOR_CHAOS_HARD_CAP

    @pytest.mark.parametrize("spec", SPECS, ids=ATTRACTOR_IDS)
    @pytest.mark.parametrize("value", ABSURD)
    def test_chaos_stays_in_0_1_at_any_dj_value(self, spec, value):
        result = eval_expr(ae.chaos_expr(spec, audience=True),
                           kick=1.0, energy=1.5, dj=value, audience=value)
        assert 0.0 <= result <= ae.ATTRACTOR_CHAOS_HARD_CAP

    @pytest.mark.parametrize("spec", SPECS, ids=ATTRACTOR_IDS)
    def test_the_audience_chaos_term_actually_does_something(self, spec):
        expr = ae.chaos_expr(spec, audience=True)
        quiet = eval_expr(expr, kick=0.0, energy=1.0, audience=0.0)
        louder = eval_expr(expr, kick=0.0, energy=1.0, audience=1.0)
        assert louder > quiet

    @pytest.mark.parametrize("spec", SPECS, ids=ATTRACTOR_IDS)
    def test_silence_with_a_full_positive_nudge_is_still_calm(self, spec):
        """A nudge is a nudge, not a new baseline."""
        result = eval_expr(ae.chaos_expr(spec, audience=True),
                           kick=0.0, energy=1.0, dj=0.0, audience=1.0)
        assert result <= spec.chaos_base + ae.ATTRACTOR_CHAOS_SPAN + 1e-9


class TestSpeedIsClamped:
    @pytest.mark.parametrize("spec", SPECS, ids=ATTRACTOR_IDS)
    @pytest.mark.parametrize("value", ABSURD)
    def test_speed_stays_within_its_window(self, spec, value):
        result = eval_expr(ae.speed_expr(spec, audience=True),
                           kick=1.0, dj=value, audience=value)
        assert ae.ATTRACTOR_SPEED_FLOOR <= result <= ae.ATTRACTOR_SPEED_HARD_CAP

    @pytest.mark.parametrize("spec", SPECS, ids=ATTRACTOR_IDS)
    def test_speed_never_reaches_zero(self, spec):
        """Zero speed freezes the form and the tail decays to a dot -- that
        reads as a crash, not as an effect."""
        result = eval_expr(ae.speed_expr(spec, audience=True),
                           kick=0.0, dj=-1.0, audience=-999.0)
        assert result >= ae.ATTRACTOR_SPEED_FLOOR


class TestTheOtherKnobsAreClamped:
    @pytest.mark.parametrize("spec", SPECS, ids=ATTRACTOR_IDS)
    @pytest.mark.parametrize("value", ABSURD)
    def test_trail_stays_in_0_1(self, spec, value):
        result = eval_expr(ae.trail_expr(spec), snare=1.0, dj=value)
        assert 0.0 <= result <= 1.0

    @pytest.mark.parametrize("spec", SPECS, ids=ATTRACTOR_IDS)
    @pytest.mark.parametrize("value", ABSURD)
    def test_spread_stays_within_its_cap(self, spec, value):
        result = eval_expr(ae.spread_expr(spec), dj=value)
        assert 0.05 <= result <= ae.ATTRACTOR_SPREAD_HARD_CAP

    @pytest.mark.parametrize("spec", SPECS, ids=ATTRACTOR_IDS)
    def test_size_stays_within_its_cap(self, spec):
        result = eval_expr(ae.size_expr(spec))
        assert 0.0 < result <= ae.ATTRACTOR_SIZE_HARD_CAP

    def test_a_spec_asking_for_an_absurd_size_is_clamped_not_honoured(self):
        spec = ae.AttractorSpec(size=999.0, spin=9999.0)
        assert eval_expr(ae.size_expr(spec)) <= ae.ATTRACTOR_SIZE_HARD_CAP
        rate = eval_expr(ae.spin_expr(spec)) / FakeAbsTime.seconds
        assert abs(rate) <= ae.ATTRACTOR_SPIN_HARD_CAP


class TestTheAudienceCannotPickAForm:
    """The morph bias is the one knob where 'bounded' means something other
    than a numeric cap: morph is cyclic, so the bound that matters is how far
    the audience can slide it, not how large it can get."""

    @pytest.mark.parametrize("spec", SPECS, ids=ATTRACTOR_IDS)
    @pytest.mark.parametrize("value", ABSURD)
    def test_the_audience_cannot_move_the_morph_by_a_whole_form(self, spec, value):
        expr = ae.morph_expr(spec, audience=True)
        neutral = eval_expr(expr, energy=1.0, dj=0.0, audience=0.0)
        driven = eval_expr(expr, energy=1.0, dj=0.0, audience=value)
        assert abs(driven - neutral) <= ae.ATTRACTOR_MORPH_SPAN + 1e-9

    def test_the_morph_span_is_smaller_than_one_form(self):
        """One form is 1.0 of morph position. If this ever stops being true,
        an audience could select an attractor, which is Thomas's decision."""
        assert ae.ATTRACTOR_MORPH_SPAN < 1.0

    @pytest.mark.parametrize("spec", SPECS, ids=ATTRACTOR_IDS)
    def test_the_dj_can_reach_every_form(self, spec):
        """The other half: Thomas's span must cover the whole ring, or the
        /dj/attractor/morph fader would be a knob that cannot do its job."""
        assert ae.DJ_SPAN["morph"] >= len(am.SEQUENCE)

    @pytest.mark.parametrize("spec", SPECS, ids=ATTRACTOR_IDS)
    def test_a_driven_morph_still_resolves_to_a_real_pair(self, spec):
        for value in ABSURD:
            position = eval_expr(ae.morph_expr(spec, audience=True),
                                 energy=1.5, dj=value, audience=value)
            a, b, w = am.morph_pair(position)
            assert a.name in am.SYSTEMS and b.name in am.SYSTEMS
            assert 0.0 <= w < 1.0


class TestAudienceFormsAreOptIn:
    """Without fx_audience installed, the rig runs exactly what it runs today."""

    @pytest.mark.parametrize("spec", SPECS, ids=ATTRACTOR_IDS)
    def test_default_expressions_never_mention_the_audience_chop(self, spec):
        for expr in (ae.chaos_expr(spec), ae.morph_expr(spec),
                     ae.speed_expr(spec), ae.trail_expr(spec),
                     ae.spread_expr(spec), ae.size_expr(spec),
                     ae.spin_expr(spec)):
            assert ae.AUDIENCE_CHOP not in expr

    @pytest.mark.parametrize("profile", ATTRACTOR_PROFILES, ids=ATTRACTOR_IDS)
    def test_the_default_plan_never_mentions_the_audience_chop(self, profile):
        plan = gp.profile_plan(profile)
        assert ae.AUDIENCE_CHOP not in repr(plan)

    @pytest.mark.parametrize("profile", ATTRACTOR_PROFILES, ids=ATTRACTOR_IDS)
    def test_the_audience_plan_does(self, profile):
        plan = gp.profile_plan(profile, audience=True)
        blob = repr(plan)
        for channel in ae.ATTRACTOR_AUDIENCE_CHANNELS:
            assert gp.aud(channel) in blob

    @pytest.mark.parametrize("profile", ATTRACTOR_PROFILES, ids=ATTRACTOR_IDS)
    def test_every_emitted_expression_evaluates(self, profile):
        """A syntax error here is a silent dead parameter at the rig."""
        for pars in gp.profile_plan(profile, audience=True).values():
            for par, value in pars.items():
                if par in ("text", "rows") or not isinstance(value, str):
                    continue
                eval_expr(value)


# ===========================================================================
# SWITCHING AWAY, AND SWITCHING BACK
# ===========================================================================
class TestANonAttractorProfileTurnsTheEngineOff:
    @pytest.mark.parametrize("name", ["UV_RAVE", "DEEP_LASER", "STROBE_ACID",
                                      "VAPOR_UV", "MONO_PULSE"])
    def test_a_silhouette_profile_writes_a_dark_attr_ctl(self, name):
        plan = gp.profile_plan(gp.PROFILES[name], audience=True)
        ctl_plan = plan[ae.CTL_CHOP]
        assert ctl_plan["enable"] == 0.0
        assert all(not isinstance(v, str) for v in ctl_plan.values()), (
            "a dark profile must leave no expression bound to evaluate")

    @pytest.mark.parametrize("profile", ATTRACTOR_PROFILES, ids=ATTRACTOR_IDS)
    def test_an_attractor_profile_enables_it(self, profile):
        plan = gp.profile_plan(profile, audience=True)
        assert plan[ae.CTL_CHOP]["enable"] == 1.0

    def test_the_dark_plan_covers_every_declared_channel(self):
        """A partial write would leave a stale knob from the previous look."""
        assert set(ae.dark_ctl_plan()) == set(ae.CTL_CHANNELS)

    @pytest.mark.parametrize("profile", ATTRACTOR_PROFILES, ids=ATTRACTOR_IDS)
    def test_the_live_plan_covers_every_declared_channel(self, profile):
        assert set(ae.attr_ctl_plan(profile.attractor)) == set(ae.CTL_CHANNELS)


# ===========================================================================
# THE DJ's OSC SURFACE
# ===========================================================================
class TestTheAttractorOscNamespace:
    def test_every_advertised_address_parses(self):
        for address in ctl.attractor_addresses():
            assert ctl.parse_osc_attractor_message(address, [0.5]) is not None

    def test_the_namespace_is_disjoint_from_both_others(self):
        for address in ctl.attractor_addresses():
            assert not address.startswith(ctl.OSC_PREFIX + "/")
            assert not address.startswith(aud.AUDIENCE_PREFIX + "/")

    def test_an_unknown_knob_is_ignored(self):
        assert ctl.parse_osc_attractor_message("/dj/attractor/rho", [1.0]) is None
        assert ctl.parse_osc_attractor_message("/dj/attractor/", [1.0]) is None
        assert ctl.parse_osc_attractor_message("/dj/attractor/a/b", [1.0]) is None

    def test_values_are_clamped_at_the_door(self):
        for raw, expected in ((999.0, 1.0), (-999.0, -1.0), (0.25, 0.25)):
            command = ctl.parse_osc_attractor_message("/dj/attractor/chaos", [raw])
            assert command["value"] == pytest.approx(expected)

    def test_non_finite_and_non_numeric_arguments_are_ignored(self):
        for bad in ([float("nan")], [float("inf")], ["loud"], [True]):
            assert ctl.parse_osc_attractor_message("/dj/attractor/chaos", bad) is None

    def test_a_profile_address_is_not_swallowed_by_this_parser(self):
        assert ctl.parse_osc_attractor_message("/dj/profile/UV_RAVE", [1.0]) is None
        assert ctl.parse_osc_attractor_message("/dj/audience/nudge/GLOW", [1.0]) is None

    def test_reset_fires_on_press_and_not_on_release(self):
        assert ctl.parse_osc_attractor_message("/dj/attractor/reset", [1.0])
        assert ctl.parse_osc_attractor_message("/dj/attractor/reset", [0.0]) is None

    def test_the_handler_routes_attractor_knobs_before_the_audience(self):
        """The routing seam, asserted in the generated handler source."""
        code = ctl.HANDLER_CODE
        assert "parse_osc_attractor_message" in code
        assert code.index("parse_osc_attractor_message") < code.index("aud.handle")
        assert "arm_lockout" in code


# ===========================================================================
# THE CONTRACT WITH THE REST OF THE RIG
# ===========================================================================
class TestContractWithTheRestOfTheRig:
    def test_the_duplicated_constants_agree(self):
        """attractor_engine copies these rather than importing them, so that
        it can be checked against dj_graphics_profiles instead of sharing its
        assumptions. Same discipline as audience_control's ceiling copy."""
        assert ae.AUDIENCE_CHOP == gp.AUDIENCE_CHOP
        assert ae.KICK == gp.KICK
        assert ae.SNARE == gp.SNARE
        assert ae.ENERGY == gp.ENERGY

    def test_every_channel_this_engine_reads_is_declared_by_the_registry(self):
        for channel in ae.ATTRACTOR_AUDIENCE_CHANNELS + ae.SHARED_AUDIENCE_CHANNELS:
            assert channel in gp.AUDIENCE_CHANNELS

    def test_the_shared_channels_are_not_owned_by_this_engine(self):
        """`speed` is the rig's existing nudge, reused rather than duplicated."""
        assert not set(ae.SHARED_AUDIENCE_CHANNELS) & set(ae.ATTRACTOR_AUDIENCE_CHANNELS)

    def test_the_nudge_maps_agree_across_all_three_files(self):
        assert set(aud.NUDGE_CHANNEL.values()) == set(gp.AUDIENCE_CHANNELS)
        assert config.NUDGE_CHANNEL == aud.NUDGE_CHANNEL
        assert set(config.NUDGE_TARGETS) == set(config.NUDGE_CHANNEL)

    def test_the_new_targets_are_reachable_through_the_airlock(self):
        for target in ("CHAOS", "MORPH"):
            command = aud.parse_audience_message(
                "%s/nudge/%s" % (aud.AUDIENCE_PREFIX, target), [0.8])
            assert command is not None
            assert command["channel"] == aud.NUDGE_CHANNEL[target]
            assert command["amount"] == pytest.approx(0.8)

    def test_the_airlock_still_clamps_the_new_targets(self):
        command = aud.parse_audience_message(
            "%s/nudge/CHAOS" % aud.AUDIENCE_PREFIX, [999.0])
        assert command["amount"] == 1.0

    def test_the_audience_cannot_reach_the_dj_channels(self):
        """attr_dj is Thomas's. There must be no audience address into it."""
        for channel in ae.DJ_CHANNELS:
            for address in ("%s/nudge/%s" % (aud.AUDIENCE_PREFIX, channel.upper()),
                            "%s/%s" % (aud.AUDIENCE_PREFIX, channel)):
                command = aud.parse_audience_message(address, [1.0])
                if command is None:
                    continue
                # SPEED is a legitimate shared nudge; it lands in fx_audience,
                # never in attr_dj.
                assert command.get("channel") in gp.AUDIENCE_CHANNELS

    def test_an_unknown_channel_raises_at_build_time(self):
        with pytest.raises(KeyError):
            ae.aud("chaoss")
        with pytest.raises(KeyError):
            ae.dj("rho")

    def test_the_engine_adds_no_chop_execute_callback(self):
        """The freeze came from onValueChange. This one is an onCook."""
        for name in ("attractor_engine.py", "attractor_math.py",
                     "attractor_pipeline.py"):
            source = (SCRIPTS / name).read_text(encoding="utf-8")
            code = "\n".join(line for line in source.splitlines()
                             if not line.lstrip().startswith("#"))
            assert "def onValueChange" not in code, name
            assert "chopexecuteDAT" not in code, name

    def test_the_engine_opens_no_audio_device(self):
        """The reactivity source must never hear anything but the music."""
        banned = ("sounddevice", "pyaudio", "simpleaudio", "playsound", "pydub",
                  "elevenlabs", "pyttsx3", "gtts", "winsound", "afplay")
        for name in ("attractor_engine.py", "attractor_math.py",
                     "attractor_pipeline.py"):
            source = (SCRIPTS / name).read_text(encoding="utf-8")
            for module in banned:
                assert "import %s" % module not in source, "%s in %s" % (module, name)

    def test_the_generated_callback_compiles(self):
        compile(ae.ENGINE_CALLBACK_CODE, "<attr_engine_cb>", "exec")

    def test_the_generated_callback_delegates_rather_than_inlines(self):
        """Logic inside a generated string cannot be unit tested, so there
        must not be any."""
        assert "attractor_engine.cook(scriptOp)" in ae.ENGINE_CALLBACK_CODE
        assert "def onCook" in ae.ENGINE_CALLBACK_CODE

    def test_the_optional_shader_uses_zero_indexed_uniform_slots(self):
        """The repo lesson: TD uniform pars are uniname0/value0x, not 1-based.
        The shader is not installed, but its wiring notes must not repeat the
        off-by-one that cost an afternoon."""
        assert "uniname0" not in ae.ATTRACTOR_GLSL_COMPUTE  # it is a comment ref
        assert "0-indexed" in ae.ATTRACTOR_GLSL_COMPUTE
        assert "uniformname1" not in ae.ATTRACTOR_GLSL_COMPUTE

    def test_the_shader_windows_match_the_python_ones(self):
        """Two implementations of one attractor is two chances to be wrong.
        The GPU path is opt-in, but its parameter windows must be the same
        numbers, or a look would change when the path did."""
        shader = ae.ATTRACTOR_GLSL_COMPUTE
        assert "lerp1(26.0, 60.0, chaos)" in shader
        assert (am.LORENZ_RHO_LO, am.LORENZ_RHO_HI) == (26.0, 60.0)
        assert "lerp1(0.21, 0.10, chaos)" in shader
        assert (am.THOMAS_B_LO, am.THOMAS_B_HI) == (0.21, 0.10)
        assert "lerp1(0.94, 1.06, chaos)" in shader
        assert (am.AIZAWA_A_LO, am.AIZAWA_A_HI) == (0.94, 1.06)
        assert "ESCAPE = %.1f" % am.ESCAPE_RADIUS in shader


class TestOutsideTouchDesigner:
    def test_importing_changes_nothing(self):
        """These modules are pasted into a live Textport. Import must not
        build, apply or enable anything."""
        assert ae._BUFFER is None or isinstance(ae._BUFFER, am.TrailBuffer)
        assert ae.attractor_stats()["cooks"] >= 0

    def test_reading_a_missing_chop_returns_the_default(self):
        assert ae._read(None, "chaos", 0.7) == 0.7

    def test_reading_a_non_finite_channel_returns_the_default(self):
        chop = FakeCHOP({"chaos": float("nan")})
        assert ae._read(chop, "chaos", 0.3) == 0.3
