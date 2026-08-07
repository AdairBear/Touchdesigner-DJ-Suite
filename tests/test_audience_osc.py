"""Offline tests for the TouchDesigner half: the audience airlock and the clamps.

Two things are proved here, and they are the two that decide whether this
feature is safe to run in front of an audience.

1. **The airlock.** ``audience_control.parse_audience_message`` and ``route``
   are pure, so the kill switch, the operator lockout, the cooldowns and the
   photosensitivity ceiling are all exercised without TouchDesigner, TouchOSC,
   a network, or an audience. The bias under test is IGNORE, exactly as in
   ``test_osc_profile_control.py``: a stray or hostile packet must never change
   the look.

2. **The clamps.** The audience-aware expressions are EVALUATED against a fake
   ``op()`` world driven to worst case -- envelopes pinned at 1.0 AND the
   audience channels pinned at absurd values -- and the existing hard caps are
   asserted to hold. A regex can be fooled by a rearranged expression; an
   evaluation cannot. This is the same technique the profile suite already uses,
   extended with the new term.

Run:  ./venv/bin/python -m pytest tests/test_audience_osc.py -v
"""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
SCRIPTS = REPO / "touchdesigner" / "scripts"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(REPO / "python"))

import audience_control as aud  # noqa: E402
import dj_graphics_profiles as gp  # noqa: E402
import osc_profile_control as ctl  # noqa: E402

ALL_PROFILES = list(gp.PROFILES.values())
PROFILE_IDS = [p.name for p in ALL_PROFILES]
NAMES = list(gp.PROFILES)
AUDIENCE_CHANNELS = tuple(gp.AUDIENCE_CHANNELS) + tuple(gp.AUDIENCE_PULSE_CHANNELS)

#: Values a hostile or broken bridge might write into fx_audience. TouchDesigner
#: itself would clamp a Constant CHOP parameter to nothing in particular, so the
#: expressions have to survive these on their own.
ABSURD = [1e9, -1e9, 999.0, -999.0, 1.0, -1.0, 0.0]


# ---------------------------------------------------------------------------
# Fake TD world, extended with fx_audience and absTime
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

    def __rtruediv__(self, other):
        return other / self._value

    def __neg__(self):
        return -self._value

    # The audience expressions wrap channel reads in min()/max(), which needs
    # ordering. A real TD channel supports these; the fake has to as well or
    # the clamp under test cannot even be evaluated.
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

    def __init__(self, by_name, by_index=None):
        self._by_name = {k: FakeChan(v) for k, v in by_name.items()}
        self._by_index = [FakeChan(v) for v in (by_index or list(by_name.values()))]

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._by_index[key]
        return self._by_name[key]


def make_op(kick=1.0, snare=1.0, energy=1.5, lfo_decay=0.0, noise=1.0,
            audience=0.0, pulse=None):
    """Build a fake ``op()`` including the audience CHOP.

    Args:
        kick: fx_kick_env['bass'].
        snare: fx_snare_env['high'].
        energy: fx_master['bass'].
        lfo_decay: fx_lfo_decay['chan1'].
        noise: fx_noise channel value.
        audience: Value written to EVERY nudge channel at once, which is the
            worst case -- a real bridge would only move one at a time.
        pulse: Overrides for the pulse channels.

    Returns:
        A callable suitable for injection as the TD ``op`` global.
    """
    channels = {name: audience for name in gp.AUDIENCE_CHANNELS}
    channels.update({name: 0.0 for name in gp.AUDIENCE_PULSE_CHANNELS})
    channels.update(pulse or {})
    world = {
        "fx_kick_env": FakeCHOP({"bass": kick}),
        "fx_snare_env": FakeCHOP({"high": snare}),
        "fx_master": FakeCHOP({"bass": energy}),
        "fx_lfo_decay": FakeCHOP({"chan1": lfo_decay}),
        "fx_noise": FakeCHOP({"chan1": noise, "chan2": noise}, [noise, noise]),
        gp.AUDIENCE_CHOP: FakeCHOP(channels),
    }
    return lambda path: world.get(path)


class FakeAbsTime:
    seconds = 1000.0
    frame = 60000


def eval_expr(expr, seconds=1000.0, **kwargs):
    """Evaluate a TD parameter expression against the fake world.

    On the deliberate ``eval``: every string comes from this repo's own
    expression builders, and standing them up the way TD would is the point --
    a regex can be fooled by a rearranged expression, an evaluation cannot.

    Args:
        expr: The expression string as emitted by a builder.
        seconds: Value for ``absTime.seconds``.
        **kwargs: Forwarded to :func:`make_op`.

    Returns:
        The numeric result.
    """
    abs_time = type("T", (), {"seconds": seconds, "frame": int(seconds * 60)})
    namespace = {
        "__builtins__": {},
        "op": make_op(**kwargs),
        "absTime": abs_time,
        "min": min, "max": max, "int": int, "abs": abs, "float": float,
    }
    return eval(expr, namespace)  # noqa: S307 - self-generated input, see docstring


# ===========================================================================
# THE CLAMPS -- every existing hard cap holds with the audience term present
# ===========================================================================
class TestAudienceCannotBreachTheHardCaps:
    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    @pytest.mark.parametrize("value", ABSURD)
    def test_glow_stays_under_the_cap_at_any_audience_value(self, profile, value):
        """Invariant 1 with strangers writing into it. The freeze cost a show."""
        result = eval_expr(gp.glow_size_expr(profile, audience=True),
                           kick=1.0, snare=1.0, audience=value)
        assert result <= gp.GLOW_SIZE_HARD_CAP

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    @pytest.mark.parametrize("value", ABSURD)
    def test_glow_never_goes_negative(self, profile, value):
        result = eval_expr(gp.glow_size_expr(profile, audience=True),
                           kick=0.0, snare=0.0, audience=value)
        assert result >= 0.0

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    @pytest.mark.parametrize("value", ABSURD)
    def test_trails_stay_below_runaway_at_any_audience_value(self, profile, value):
        """Invariant 2. At >= 1.0 the feedback whites out the frame."""
        result = eval_expr(gp.trail_valuemult_expr(profile, audience=True),
                           energy=1.5, lfo_decay=0.0, audience=value)
        assert result <= gp.TRAIL_VALUEMULT_HARD_CAP
        assert result >= 0.0

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    @pytest.mark.parametrize("value", ABSURD)
    def test_kick_flash_stays_under_its_cap(self, profile, value):
        result = eval_expr(gp.kick_flash_expr(profile, audience=True),
                           kick=1.0, audience=value,
                           pulse={"strobe_t0": 1000.0, "strobe_dur": 1.5,
                                  "white_t0": 1000.0, "white_dur": 0.6})
        assert result <= gp.KICK_FLASH_HARD_CAP

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    @pytest.mark.parametrize("value", ABSURD)
    def test_zoom_stays_within_bounds(self, profile, value):
        result = eval_expr(gp.zoom_expr(profile, audience=True),
                           kick=1.0, audience=value)
        assert 1.0 <= result <= gp.ZOOM_HARD_CAP

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    @pytest.mark.parametrize("value", ABSURD)
    def test_shake_stays_proportional_and_bounded(self, profile, value):
        """The audience scales the profile's shake; it cannot invent its own."""
        ceiling = abs(profile.shake_snare_px / 1280.0) * (1 + gp.AUDIENCE_SHAKE_SPAN)
        result = eval_expr(gp.shake_expr(profile, 0, audience=True),
                           snare=1.0, noise=1.0, audience=value)
        assert abs(result) <= ceiling + 1e-9

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    def test_silence_with_a_full_positive_nudge_is_still_calm(self, profile):
        """A nudge is a nudge, not a new baseline: no music, no explosion."""
        glow = eval_expr(gp.glow_size_expr(profile, audience=True),
                         kick=0.0, snare=0.0, audience=1.0)
        assert glow <= gp.GLOW_SIZE_BASE + gp.AUDIENCE_GLOW_SPAN

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    def test_the_audience_term_actually_does_something(self, profile):
        """Safety that clamps to a no-op is not safety, it is a broken feature."""
        expr = gp.glow_size_expr(profile, audience=True)
        quiet = eval_expr(expr, kick=0.0, snare=0.0, audience=0.0)
        louder = eval_expr(expr, kick=0.0, snare=0.0, audience=1.0)
        assert louder > quiet


class TestAudienceFormsAreOptIn:
    """Without fx_audience installed, the rig runs exactly what it runs today."""

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    def test_default_expressions_never_mention_the_audience_chop(self, profile):
        builders = [
            gp.glow_size_expr(profile),
            gp.trail_valuemult_expr(profile),
            gp.kick_flash_expr(profile),
            gp.zoom_expr(profile),
            gp.shake_expr(profile, 0),
            gp.shake_expr(profile, 1),
            gp.outline_bright_expr(profile),
            gp.mode_index_expr(profile),
            gp.palette_engine_code(profile),
        ]
        for expr in builders:
            assert gp.AUDIENCE_CHOP not in expr

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    def test_the_default_plan_writes_plain_tint_values_not_expressions(self, profile):
        tint = gp.profile_plan(profile)["fire_tint"]
        assert [tint["colorr"], tint["colorg"], tint["colorb"]] == list(profile.fire_tint)

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    def test_the_audience_plan_binds_every_audience_channel_somewhere(self, profile):
        plan = gp.profile_plan(profile, audience=True)
        blob = repr(plan)
        for channel in gp.AUDIENCE_CHANNELS:
            assert "'%s'" % channel in blob, "%s is declared but never read" % channel


# ===========================================================================
# THE COLOUR SNAP -- the palette guard, applied to the new surface
# ===========================================================================
class TestColourPopCannotProduceBrown:
    """A lerp would cross the banned hue band. A snap cannot.

    This is not an argument, it is a measurement: the tint expression is
    evaluated at both ends of its gate for every (profile, anchor) pair, and
    both ends are put through the existing ``is_brown`` / ``is_neon`` guards.
    """

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    @pytest.mark.parametrize("anchor", ["CYAN", "MAGENTA", "ACID", "PINK",
                                        "VIOLET", "BLUE", "WHITE_HOT"])
    def test_both_ends_of_the_snap_pass_the_palette_guards(self, profile, anchor):
        rgb = getattr(gp, anchor)
        exprs = [gp.fire_tint_expr(profile, i) for i in range(3)]

        closed = tuple(eval_expr(e, pulse={"pop_t0": -1e9, "pop_dur": 0.0,
                                           "pop_r": rgb[0], "pop_g": rgb[1],
                                           "pop_b": rgb[2]}) for e in exprs)
        assert closed == pytest.approx(profile.fire_tint)

        opened = tuple(eval_expr(e, seconds=1000.0,
                                 pulse={"pop_t0": 999.5, "pop_dur": 2.0,
                                        "pop_r": rgb[0], "pop_g": rgb[1],
                                        "pop_b": rgb[2]}) for e in exprs)
        assert opened == pytest.approx(rgb)
        for colour in (closed, opened):
            assert not gp.is_brown(colour)
            assert gp.is_neon(colour)

    def test_a_naive_crossfade_would_have_produced_brown(self):
        """Why the snap exists. If this ever stops failing, re-check the snap."""
        muddy = []
        for anchor in (gp.MAGENTA, gp.ACID, gp.PINK, gp.VIOLET):
            for profile in ALL_PROFILES:
                for step in range(21):
                    f = step / 20.0
                    mix = tuple(profile.fire_tint[c] + (anchor[c] - profile.fire_tint[c]) * f
                                for c in range(3))
                    if gp.is_brown(mix):
                        muddy.append((profile.name, mix))
        assert muddy, "a lerp used to cross the brown band; the snap avoids it"

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    def test_the_tint_is_bounded_to_zero_one_whatever_is_written(self, profile):
        for junk in (1e9, -1e9, 42.0):
            for i in range(3):
                value = eval_expr(gp.fire_tint_expr(profile, i),
                                  pulse={"pop_t0": 999.5, "pop_dur": 2.0,
                                         "pop_r": junk, "pop_g": junk,
                                         "pop_b": junk})
                assert 0.0 <= value <= 1.0


# ===========================================================================
# THE PULSE -- self-cancelling, and rate-capped
# ===========================================================================
class TestOneShotPulses:
    def test_a_pulse_is_closed_by_default(self):
        """Zeroed channels must mean 'no effect', not 'permanently on'."""
        gate = gp.pulse_gate_expr("pop_t0", "pop_dur")
        assert eval_expr(gate, seconds=1000.0) == 0.0

    def test_a_pulse_opens_inside_its_window_and_closes_after(self):
        gate = gp.pulse_gate_expr("strobe_t0", "strobe_dur")
        inside = eval_expr(gate, seconds=100.5,
                           pulse={"strobe_t0": 100.0, "strobe_dur": 1.5})
        after = eval_expr(gate, seconds=102.0,
                          pulse={"strobe_t0": 100.0, "strobe_dur": 1.5})
        assert inside == 1.0 and after == 0.0

    def test_a_pulse_self_cancels_without_anything_switching_it_off(self):
        """A bridge that dies mid-burst leaves an effect that expires anyway."""
        gate = gp.pulse_gate_expr("white_t0", "white_dur")
        for elapsed in (0.0, 0.3, 0.59, 0.61, 5.0, 3600.0):
            value = eval_expr(gate, seconds=100.0 + elapsed,
                              pulse={"white_t0": 100.0, "white_dur": 0.6})
            assert value == (1.0 if elapsed < 0.6 else 0.0)

    def test_the_decay_envelope_falls_to_zero(self):
        decay = gp.pulse_decay_expr("white_t0", "white_dur")
        start = eval_expr(decay, seconds=100.0,
                          pulse={"white_t0": 100.0, "white_dur": 0.6})
        mid = eval_expr(decay, seconds=100.3,
                        pulse={"white_t0": 100.0, "white_dur": 0.6})
        end = eval_expr(decay, seconds=100.6,
                        pulse={"white_t0": 100.0, "white_dur": 0.6})
        after = eval_expr(decay, seconds=200.0,
                          pulse={"white_t0": 100.0, "white_dur": 0.6})
        assert start == pytest.approx(1.0)
        assert 0.4 < mid < 0.6
        assert end == pytest.approx(0.0, abs=1e-9)
        assert after == 0.0

    def test_the_strobe_flashes_no_faster_than_the_ceiling(self):
        """Counted, not asserted from the constant: sample the term over a second."""
        term = gp.strobe_term_expr()
        samples = [eval_expr(term, seconds=100.0 + i / 240.0,
                             pulse={"strobe_t0": 100.0, "strobe_dur": 1.5})
                   for i in range(240)]
        transitions = sum(1 for a, b in zip(samples, samples[1:])
                          if (a > 0) != (b > 0))
        # One flash is an on/off pair, so transitions/2 is flashes per second.
        flashes_per_second = transitions / 2.0
        assert flashes_per_second <= 3.0, "WCAG 2.3.1 general flash threshold"
        assert flashes_per_second == pytest.approx(gp.STROBE_HZ_CAP, abs=0.5), (
            "the constant must mean flashes per second, not half of it")

    def test_the_strobe_rate_is_a_literal_not_a_channel_read(self):
        """No value the audience writes can change the flash rate."""
        term = gp.strobe_term_expr()
        assert "%g" % (2.0 * gp.STROBE_HZ_CAP) in term
        assert "strobe_hz" not in term and "['speed']" not in term

    def test_strobe_and_whiteout_together_still_respect_the_flash_cap(self):
        for profile in ALL_PROFILES:
            value = eval_expr(gp.kick_flash_expr(profile, audience=True),
                              seconds=100.0, kick=1.0, audience=1.0,
                              pulse={"strobe_t0": 100.0, "strobe_dur": 1.5,
                                     "white_t0": 100.0, "white_dur": 0.6})
            assert value <= gp.KICK_FLASH_HARD_CAP


# ===========================================================================
# THE AIRLOCK -- gate 3, which does not trust the bridge
# ===========================================================================
class TestAudienceAirlock:
    @pytest.mark.parametrize("name", NAMES, ids=NAMES)
    def test_a_registered_profile_resolves(self, name):
        command = aud.parse_audience_message(
            "%s/profile/%s" % (aud.AUDIENCE_PREFIX, name), [1.0])
        assert command == {"kind": "profile", "target": name}

    @pytest.mark.parametrize("address", [
        "/dj/audience/profile/UV_RAVE_2",
        "/dj/audience/profile/",
        "/dj/audience/profile/../../panic",
        "/dj/audience/nudge/EXEC",
        "/dj/audience/oneshot/MEGA_STROBE",
        "/dj/audience/exec/rm",
        "/dj/audience",
        "/dj/audience/",
        "/random/thing",
        "",
        "/dj/audience/profile/UV_RAVE/extra",
    ])
    def test_anything_off_list_is_ignored(self, address):
        assert aud.parse_audience_message(address, [1.0]) is None

    def test_a_button_release_does_not_re_apply(self):
        addr = "%s/profile/%s" % (aud.AUDIENCE_PREFIX, NAMES[0])
        assert aud.parse_audience_message(addr, [0.0]) is None
        assert aud.parse_audience_message(addr, [False]) is None

    @pytest.mark.parametrize("amount,expected", [
        (0.5, 0.5), (-0.5, -0.5), (999.0, 1.0), (-999.0, -1.0),
    ])
    def test_nudge_amounts_are_re_clamped_at_the_airlock(self, amount, expected):
        command = aud.parse_audience_message(
            "%s/nudge/GLOW" % aud.AUDIENCE_PREFIX, [amount])
        assert command["amount"] == expected
        assert command["channel"] == "gain_glow"

    @pytest.mark.parametrize("junk", [float("inf"), float("nan"), "1.0",
                                      None, [1.0]])
    def test_a_non_numeric_or_non_finite_nudge_is_ignored(self, junk):
        assert aud.parse_audience_message(
            "%s/nudge/GLOW" % aud.AUDIENCE_PREFIX, [junk]) is None

    def test_a_colour_pop_resolves_only_to_a_registry_anchor(self):
        command = aud.parse_audience_message(
            "%s/oneshot/COLOR_POP" % aud.AUDIENCE_PREFIX, [2.0, "ACID"])
        assert command["colour"] == gp.ACID

    @pytest.mark.parametrize("colour", ["BROWN", "PROFILES", "is_brown",
                                        "__builtins__", "#ff8800", "", "PARENT"])
    def test_a_colour_pop_cannot_name_an_arbitrary_module_attribute(self, colour):
        """The lookup is a getattr, so this is the test that keeps it honest."""
        assert aud.parse_audience_message(
            "%s/oneshot/COLOR_POP" % aud.AUDIENCE_PREFIX, [2.0, colour]) is None

    def test_a_colour_pop_without_a_colour_is_ignored(self):
        assert aud.parse_audience_message(
            "%s/oneshot/COLOR_POP" % aud.AUDIENCE_PREFIX, [2.0]) is None

    def test_the_airlock_reads_the_live_registry(self):
        temp = gp.Profile(name="AIRLOCK_TEMP", description="test",
                          palette=[gp.CYAN, gp.BLUE], fire_tint=gp.VIOLET)
        gp.PROFILES["AIRLOCK_TEMP"] = temp
        try:
            assert aud.parse_audience_message(
                "%s/profile/AIRLOCK_TEMP" % aud.AUDIENCE_PREFIX, [1.0]) is not None
        finally:
            del gp.PROFILES["AIRLOCK_TEMP"]
        assert aud.parse_audience_message(
            "%s/profile/AIRLOCK_TEMP" % aud.AUDIENCE_PREFIX, [1.0]) is None


class TestKillSwitchIsIndependent:
    def test_disabled_blocks_every_audience_verb(self):
        state = aud.AudienceState()
        state.enabled = False
        for address, args in (
                ("%s/profile/%s" % (aud.AUDIENCE_PREFIX, NAMES[0]), [1.0]),
                ("%s/nudge/GLOW" % aud.AUDIENCE_PREFIX, [0.5]),
                ("%s/oneshot/WHITEOUT" % aud.AUDIENCE_PREFIX, [0.6])):
            assert aud.route(address, args, state, now=0.0) is None
        assert state.rejected["disabled"] == 3

    def test_disabling_the_audience_does_not_disable_thomas(self):
        """The single most important detail in the override design.

        His buttons are a different namespace and a different parser, so the
        audience gate cannot reach them however it is set.
        """
        state = aud.AudienceState()
        state.enabled = False
        for name in NAMES:
            assert ctl.parse_osc_profile_message("/dj/profile/%s" % name, [1.0]) == name

    def test_a_rogue_bridge_cannot_forge_thomas_namespace_through_this_module(self):
        state = aud.AudienceState()
        for name in NAMES:
            assert aud.route("/dj/profile/%s" % name, [1.0], state, now=0.0) is None

    def test_the_kill_switch_survives_a_still_flushing_bridge(self):
        """A hung bridge keeps sending. TD stops listening anyway."""
        state = aud.AudienceState()
        aud.route("%s/enable" % aud.AUDIENCE_PREFIX, [0.0], state, now=0.0)
        blocked = 0
        for i in range(50):
            if aud.route("%s/nudge/GLOW" % aud.AUDIENCE_PREFIX, [1.0], state,
                         now=i * 30.0) is None:
                blocked += 1
        assert blocked == 50

    def test_enable_can_be_turned_back_on(self):
        state = aud.AudienceState()
        aud.route("%s/enable" % aud.AUDIENCE_PREFIX, [0.0], state, now=0.0)
        aud.route("%s/enable" % aud.AUDIENCE_PREFIX, [1.0], state, now=1.0)
        assert aud.route("%s/nudge/GLOW" % aud.AUDIENCE_PREFIX, [0.5], state,
                         now=2.0) is not None


class TestOperatorPriorityTdSide:
    def test_a_lockout_suppresses_audience_traffic_but_self_clears(self):
        state = aud.AudienceState()
        state.arm_lockout(0.0)
        assert aud.route("%s/nudge/GLOW" % aud.AUDIENCE_PREFIX, [0.5], state,
                         now=10.0) is None
        assert aud.route("%s/nudge/GLOW" % aud.AUDIENCE_PREFIX, [0.5], state,
                         now=aud.OPERATOR_LOCKOUT_S + 1) is not None

    def test_panic_re_enables_and_holds_the_room_for_five_minutes(self):
        """PANIC must work even if the audience gate was left in a weird state."""
        state = aud.AudienceState()
        state.enabled = False
        command = aud.route("/dj/panic", [1.0], state, now=0.0)
        assert command == {"kind": "panic"}
        assert state.enabled is True
        assert state.locked_out(aud.PANIC_LOCKOUT_S - 1)
        assert not state.locked_out(aud.PANIC_LOCKOUT_S)

    def test_panic_release_does_not_re_fire(self):
        assert aud.parse_audience_message("/dj/panic", [0.0]) is None

    def test_profile_lock_leaves_nudges_and_oneshots_alone(self):
        state = aud.AudienceState()
        aud.route("%s/lock_profile" % aud.AUDIENCE_PREFIX, [1.0], state, now=0.0)
        assert aud.route("%s/profile/%s" % (aud.AUDIENCE_PREFIX, NAMES[1]),
                         [1.0], state, now=0.0) is None
        assert aud.route("%s/nudge/ZOOM" % aud.AUDIENCE_PREFIX, [0.5], state,
                         now=0.0) is not None

    def test_the_gain_dial_scales_what_arrives(self):
        state = aud.AudienceState()
        aud.route("%s/gain" % aud.AUDIENCE_PREFIX, [0.3], state, now=0.0)
        command = aud.route("%s/nudge/GLOW" % aud.AUDIENCE_PREFIX, [1.0], state,
                            now=0.0)
        assert command["amount"] == pytest.approx(0.3)

    @pytest.mark.parametrize("gain", [5.0, -1.0, 1e9])
    def test_an_out_of_range_gain_cannot_amplify(self, gain):
        state = aud.AudienceState()
        aud.route("%s/gain" % aud.AUDIENCE_PREFIX, [gain], state, now=0.0)
        assert 0.0 <= state.gain <= 1.0


class TestTdSideCeiling:
    """Enforced here too, independently, so a compromised bridge gains nothing."""

    def test_a_bridge_asking_for_a_ten_second_strobe_gets_one_and_a_half(self):
        state = aud.AudienceState()
        command = aud.route("%s/oneshot/STROBE_BURST" % aud.AUDIENCE_PREFIX,
                            [10.0], state, now=0.0)
        assert command["duration"] == aud.ONESHOT_LIMITS["STROBE_BURST"][0]

    def test_the_requested_duration_is_never_read_at_all(self):
        state_a, state_b = aud.AudienceState(), aud.AudienceState()
        a = aud.route("%s/oneshot/WHITEOUT" % aud.AUDIENCE_PREFIX, [0.01],
                      state_a, now=0.0)
        b = aud.route("%s/oneshot/WHITEOUT" % aud.AUDIENCE_PREFIX, [9999.0],
                      state_b, now=0.0)
        assert a["duration"] == b["duration"]

    def test_a_flood_of_strobe_requests_yields_one_per_interval(self):
        state = aud.AudienceState()
        emitted = 0
        for i in range(2000):
            now = i * 0.05
            if aud.route("%s/oneshot/STROBE_BURST" % aud.AUDIENCE_PREFIX,
                         [1.5], state, now=now) is not None:
                emitted += 1
        span = 2000 * 0.05
        assert emitted <= span / aud.ONESHOT_LIMITS["STROBE_BURST"][1] + 1
        assert emitted >= 1, "the ceiling limits, it does not disable"

    def test_the_td_side_cooldowns_hold_without_the_bridge(self):
        state = aud.AudienceState()
        assert aud.route("%s/profile/%s" % (aud.AUDIENCE_PREFIX, NAMES[1]),
                         [1.0], state, now=0.0) is not None
        assert aud.route("%s/profile/%s" % (aud.AUDIENCE_PREFIX, NAMES[2]),
                         [1.0], state, now=5.0) is None
        assert aud.route("%s/profile/%s" % (aud.AUDIENCE_PREFIX, NAMES[2]),
                         [1.0], state, now=61.0) is not None


class TestContractWithTheRestOfTheRig:
    def test_the_audience_namespace_is_disjoint_from_thomas(self):
        for address in aud.audience_addresses():
            if address == aud.PANIC_ADDRESS:
                continue
            assert not address.startswith(ctl.OSC_PREFIX + "/")

    def test_every_advertised_address_actually_parses(self):
        for address in aud.audience_addresses():
            args = [1.0, "ACID"] if address.endswith("COLOR_POP") else [1.0]
            assert aud.parse_audience_message(address, args) is not None, address

    def test_thomas_addresses_are_untouched_by_this_change(self):
        for name in NAMES:
            assert ctl.parse_osc_profile_message("/dj/profile/%s" % name, [1.0]) == name
        assert ctl.parse_osc_profile_message("/dj/profile", [NAMES[0]]) == NAMES[0]

    def test_the_handler_offers_unmatched_packets_to_the_audience_module(self):
        """The routing seam, asserted in the generated handler source."""
        assert "audience_control" in ctl.HANDLER_CODE
        assert "aud.handle(address, args)" in ctl.HANDLER_CODE
        assert "arm_lockout" in ctl.HANDLER_CODE

    def test_every_nudge_target_maps_to_a_declared_channel(self):
        assert set(aud.NUDGE_CHANNEL.values()) == set(gp.AUDIENCE_CHANNELS)

    def test_the_pulse_channels_are_all_read_by_some_expression(self):
        blob = "".join([
            gp.strobe_term_expr(), gp.whiteout_term_expr(),
            gp.fire_tint_expr(ALL_PROFILES[0], 0),
            gp.fire_tint_expr(ALL_PROFILES[0], 1),
            gp.fire_tint_expr(ALL_PROFILES[0], 2),
        ])
        for channel in gp.AUDIENCE_PULSE_CHANNELS:
            assert "'%s'" % channel in blob, "%s is written but never read" % channel

    def test_an_unknown_audience_channel_raises_at_build_time(self):
        with pytest.raises(KeyError):
            gp.aud("gain_gllow")

    def test_the_td_module_adds_no_chop_execute_callback(self):
        """The freeze came from onValueChange. This one fires on a UDP packet."""
        source = (SCRIPTS / "audience_control.py").read_text(encoding="utf-8")
        code = "\n".join(line for line in source.splitlines()
                         if not line.lstrip().startswith("#"))
        assert "def onValueChange" not in code
        assert "chopexecuteDAT" not in code
