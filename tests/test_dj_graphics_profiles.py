"""Offline tests for the swappable graphics profiles (dj_graphics_profiles.py).

The module is deliberately split so the interesting half needs no TouchDesigner:
the profile registry, the palette guard, and every parameter-expression builder
are pure Python. These tests therefore prove the two things that actually matter
at the rig, on a laptop, with no TD and no audio:

  1. FREEZE SAFETY. The module adds no audio tap and no CHOP Execute DAT, and
     the glow-size expression it emits stays clamped even when the kick and
     snare envelopes are pinned at 1.0. The freeze cost a live show; it is
     asserted here rather than eyeballed.
  2. TRAIL RUNAWAY. The feedback value-multiply expression stays below 1.0 for
     every profile at maximum energy, so no look can white out the frame.

Rather than pattern-match the expression strings, the clamp tests EVALUATE them
against a fake ``op()`` world driven to worst-case values. A regex can be fooled
by a rearranged expression; ``eval`` cannot.

Run:  ./venv/bin/python -m pytest tests/test_dj_graphics_profiles.py -v
"""

import sys
from pathlib import Path

import pytest

# The module lives under touchdesigner/scripts, not python/ (which conftest adds).
SCRIPTS = Path(__file__).parent.parent / "touchdesigner" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import dj_graphics_profiles as gp  # noqa: E402


# ---------------------------------------------------------------------------
# Fake TD world, just rich enough to evaluate a parameter expression.
# ---------------------------------------------------------------------------
class FakeChan:
    """A CHOP channel that reports a fixed value."""

    def __init__(self, value):
        self._value = value

    def eval(self):
        return self._value

    def __float__(self):
        return float(self._value)

    # TD expressions use the channel directly in arithmetic.
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


class FakeCHOP:
    """A CHOP whose channels are addressable by name or index."""

    def __init__(self, by_name, by_index=None):
        self._by_name = {k: FakeChan(v) for k, v in by_name.items()}
        self._by_index = [FakeChan(v) for v in (by_index or list(by_name.values()))]

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._by_index[key]
        return self._by_name[key]


def make_op(kick=1.0, snare=1.0, energy=1.5, lfo_decay=0.0, noise=1.0):
    """Build a fake ``op()`` resolving the CHOPs the expressions reference.

    Defaults are the worst case for the safety clamps: envelopes pinned on, the
    energy accumulator at the top of its 0.6..1.5 range, and the LFO at the
    value that subtracts least from trail decay.

    Args:
        kick: fx_kick_env['bass'] value.
        snare: fx_snare_env['high'] value.
        energy: fx_master['bass'] value.
        lfo_decay: fx_lfo_decay['chan1'] value.
        noise: fx_noise channel value.

    Returns:
        A callable suitable for injection as the TD ``op`` global.
    """
    world = {
        "fx_kick_env": FakeCHOP({"bass": kick}),
        "fx_snare_env": FakeCHOP({"high": snare}),
        "fx_master": FakeCHOP({"bass": energy}),
        "fx_lfo_decay": FakeCHOP({"chan1": lfo_decay}),
        "fx_noise": FakeCHOP({"chan1": noise, "chan2": noise}, [noise, noise]),
    }
    return lambda path: world.get(path)


class FakeAbsTime:
    seconds = 123.4
    frame = 7404


def eval_expr(expr, **kwargs):
    """Evaluate a TD parameter expression against the fake world.

    On the deliberate ``eval``: the input is never untrusted. Every string comes
    from this repo's own expression builders, and standing them up the way TD
    would is the entire point of the test -- a regex can be fooled by a
    rearranged expression, an evaluation cannot. ``ast.literal_eval`` cannot
    substitute here because these are expressions with calls (``op()``,
    ``min()``), not literals. The namespace is restricted to the handful of
    names TD itself exposes, with no builtins.

    Args:
        expr: The expression string as emitted by a builder.
        **kwargs: Forwarded to ``make_op`` to drive the envelopes.

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
    return eval(expr, namespace)  # noqa: S307 - self-generated input, see docstring


ALL_PROFILES = list(gp.PROFILES.values())
PROFILE_IDS = [p.name for p in ALL_PROFILES]


# ---------------------------------------------------------------------------
# Registry + palette constraint (neon/UV, brown removed)
# ---------------------------------------------------------------------------
class TestRegistry:
    def test_registry_is_populated(self):
        assert len(gp.PROFILES) >= 4, "expected a useful spread of pre-show looks"

    def test_default_profile_exists(self):
        assert gp.DEFAULT_PROFILE in gp.PROFILES

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    def test_every_shipped_profile_is_valid(self, profile):
        """No registered profile may violate the palette or safety rules."""
        assert gp.validate_profile(profile) == []

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    def test_no_profile_contains_brown(self, profile):
        """The neon/UV constraint: the orange band that muddied to brown is gone."""
        for rgb in list(profile.palette) + [profile.fire_tint]:
            assert not gp.is_brown(rgb), "%s has brown-forming %s" % (profile.name, rgb)

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    def test_every_colour_reads_as_neon(self, profile):
        for rgb in list(profile.palette) + [profile.fire_tint]:
            assert gp.is_neon(rgb), "%s has non-neon %s" % (profile.name, rgb)


class TestBrownGuard:
    def test_the_original_offending_orange_is_rejected(self):
        """(1.0, 0.42, 0.0) is the anchor from the palette that browned."""
        assert gp.is_brown((1.0, 0.42, 0.0))

    def test_actual_brown_is_rejected(self):
        assert gp.is_brown((0.4, 0.26, 0.13))

    @pytest.mark.parametrize("rgb", [
        (0.0, 1.0, 1.0),    # cyan
        (1.0, 0.0, 1.0),    # magenta
        (0.35, 1.0, 0.06),  # acid green
        (1.0, 0.06, 0.55),  # hot pink
        (0.6, 0.0, 1.0),    # violet
    ])
    def test_neon_anchors_pass_both_guards(self, rgb):
        assert not gp.is_brown(rgb)
        assert gp.is_neon(rgb)

    def test_validation_rejects_a_brown_profile(self):
        bad = gp.Profile(
            name="BAD", description="has orange",
            palette=[(0.0, 1.0, 1.0), (1.0, 0.42, 0.0)],
            fire_tint=(1.0, 0.1, 0.9),
        )
        problems = gp.validate_profile(bad)
        assert any("brown" in p for p in problems)


# ---------------------------------------------------------------------------
# INVARIANT 1 -- the freeze
# ---------------------------------------------------------------------------
class TestFreezeSafety:
    """The graphics froze under real audio. These guard the fix."""

    def test_module_adds_no_chop_execute_callback(self):
        """onValueChange fires once per FFT bin; that is what froze the cook."""
        source = (SCRIPTS / "dj_graphics_profiles.py").read_text()
        code_lines = [
            line for line in source.splitlines()
            if not line.lstrip().startswith("#")
        ]
        code = "\n".join(code_lines)
        assert "def onValueChange" not in code
        assert "chopexecuteDAT" not in code
        assert "chopExecuteDAT" not in code

    def test_module_taps_no_audio_operators_directly(self):
        """All reactivity must ride the existing envelope CHOPs, not the FFT."""
        source = (SCRIPTS / "dj_graphics_profiles.py").read_text()
        code = "\n".join(
            line for line in source.splitlines() if not line.lstrip().startswith("#")
        )
        for forbidden in ("audio_spectrum", "audio_in", "audio_amp"):
            assert forbidden not in code, "must not tap %s" % forbidden

    def test_palette_engine_is_a_script_chop_oncook(self):
        """onCook runs once per cook. That is the safe shape."""
        for profile in ALL_PROFILES:
            code = gp.palette_engine_code(profile)
            assert "def onCook(scriptOp):" in code
            assert "def onValueChange" not in code

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    def test_glow_expression_is_clamped_at_full_drive(self, profile):
        """Evaluated, not pattern-matched: pin both envelopes and check the cap."""
        value = eval_expr(gp.glow_size_expr(profile), kick=1.0, snare=1.0)
        assert value <= gp.GLOW_SIZE_HARD_CAP, (
            "%s glow reaches %.1fpx, above the %.1fpx cap that keeps the cook alive"
            % (profile.name, value, gp.GLOW_SIZE_HARD_CAP)
        )

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    def test_glow_stays_clamped_under_absurd_input(self, profile):
        """A misbehaving envelope must not be able to explode the blur either."""
        value = eval_expr(gp.glow_size_expr(profile), kick=50.0, snare=50.0)
        assert value <= gp.GLOW_SIZE_HARD_CAP

    def test_glow_builder_cannot_emit_an_unclamped_form(self):
        """Even a profile asking for an enormous blur gets the min() form."""
        greedy = gp.Profile(
            name="GREEDY", description="asks for too much blur",
            palette=[(0.0, 1.0, 1.0), (1.0, 0.0, 1.0)], fire_tint=(1.0, 0.1, 0.9),
            glow_kick_gain=10000.0, glow_snare_gain=10000.0,
        )
        expr = gp.glow_size_expr(greedy)
        assert "min(" in expr
        assert eval_expr(expr, kick=1.0, snare=1.0) <= gp.GLOW_SIZE_HARD_CAP

    def test_glow_still_moves_meaningfully(self):
        """A clamp that flattens the reactivity would be its own failure."""
        profile = gp.PROFILES["UV_RAVE"]
        silent = eval_expr(gp.glow_size_expr(profile), kick=0.0, snare=0.0)
        loud = eval_expr(gp.glow_size_expr(profile), kick=1.0, snare=1.0)
        assert loud - silent >= 20.0, "glow must visibly punch, not just twitch"


# ---------------------------------------------------------------------------
# INVARIANT 2 -- trail runaway
# ---------------------------------------------------------------------------
class TestTrailRunaway:
    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    def test_valuemult_stays_below_one_at_max_energy(self, profile):
        """>= 1.0 on a Feedback TOP accumulates forever and whites out."""
        value = eval_expr(gp.trail_valuemult_expr(profile), energy=1.5, lfo_decay=0.0)
        assert value < 1.0, "%s trails would run away (%.4f)" % (profile.name, value)
        assert value <= gp.TRAIL_VALUEMULT_HARD_CAP

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    def test_valuemult_stays_positive_at_min_energy(self, profile):
        """A negative multiply would invert the trail instead of fading it."""
        value = eval_expr(gp.trail_valuemult_expr(profile), energy=0.6, lfo_decay=1.0)
        assert value > 0.0

    def test_runaway_profile_is_clamped_on_emit(self):
        greedy = gp.Profile(
            name="GREEDY", description="asks for infinite trails",
            palette=[(0.0, 1.0, 1.0), (1.0, 0.0, 1.0)], fire_tint=(1.0, 0.1, 0.9),
            trail_persistence=5.0, trail_energy_gain=5.0,
        )
        assert eval_expr(gp.trail_valuemult_expr(greedy), energy=1.5) <= (
            gp.TRAIL_VALUEMULT_HARD_CAP
        )

    def test_validation_flags_a_runaway_persistence(self):
        greedy = gp.Profile(
            name="GREEDY", description="x",
            palette=[(0.0, 1.0, 1.0), (1.0, 0.0, 1.0)], fire_tint=(1.0, 0.1, 0.9),
            trail_persistence=1.2,
        )
        assert any("run away" in p for p in gp.validate_profile(greedy))

    def test_energy_term_dropped_when_fx_master_absent(self):
        """Without the accumulator we must not bind a dead op reference."""
        profile = gp.PROFILES["UV_RAVE"]
        expr = gp.trail_valuemult_expr(profile, with_energy=False)
        assert "fx_master" not in expr

    def test_energy_actually_lengthens_trails(self):
        """The new energy dimension has to do something, or it is decoration."""
        profile = gp.PROFILES["MONO_PULSE"]
        quiet = eval_expr(gp.trail_valuemult_expr(profile), energy=0.6)
        busy = eval_expr(gp.trail_valuemult_expr(profile), energy=1.5)
        assert busy > quiet


# ---------------------------------------------------------------------------
# Reactivity must be REAL and MULTI-EFFECT, not one blur
# ---------------------------------------------------------------------------
class TestReactivityIsMultiEffect:
    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    def test_kick_and_snare_each_drive_several_distinct_nodes(self, profile):
        plan = gp.profile_plan(profile)
        kick_nodes, snare_nodes = set(), set()
        for node, pars in plan.items():
            for value in pars.values():
                text = str(value)
                if "fx_kick_env" in text:
                    kick_nodes.add(node)
                if "fx_snare_env" in text:
                    snare_nodes.add(node)
        assert len(kick_nodes) >= 4, "kick drives only %s" % sorted(kick_nodes)
        assert len(snare_nodes) >= 2, "snare drives only %s" % sorted(snare_nodes)

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    def test_reactivity_spans_distinct_effect_types(self, profile):
        """Colour, brightness, blur, geometry -- not four flavours of one thing."""
        plan = gp.profile_plan(profile)
        assert "fx_kick_env" in str(plan["outline_level"]["brightness1"])  # brightness
        assert "fx_kick_env" in str(plan["outline_glow"]["size"])          # blur
        assert "fx_kick_env" in str(plan["fx_kick_expand"]["scale"])       # geometry
        assert "fx_snare_env" in str(plan["fx_snare_shake"]["tx"])         # displacement
        assert "fx_kick_env" in plan["fx_palette_engine_cb"]["text"]       # colour
        assert "fx_snare_env" in plan["fx_palette_engine_cb"]["text"]      # colour

    def test_energy_accumulator_is_used_somewhere(self):
        used = [
            p.name for p in ALL_PROFILES
            if "fx_master" in str(gp.profile_plan(p)["fx_trail_hsv"]["valuemult"])
        ]
        assert used, "the 30s energy accumulator drives nothing"


# ---------------------------------------------------------------------------
# Profiles must be genuinely different, not recolours
# ---------------------------------------------------------------------------
class TestProfilesAreDifferentiated:
    def test_palettes_are_distinct(self):
        seen = {tuple(p.palette) for p in ALL_PROFILES}
        assert len(seen) == len(ALL_PROFILES)

    def test_trail_persistence_spans_a_wide_range(self):
        values = [p.trail_persistence for p in ALL_PROFILES]
        assert max(values) - min(values) >= 0.15, (
            "profiles differ in colour but not in feel: %s" % values
        )

    def test_reactivity_gains_differ_across_profiles(self):
        gains = {(p.outline_kick_gain, p.zoom_kick_gain, p.kick_flash_gain)
                 for p in ALL_PROFILES}
        assert len(gains) == len(ALL_PROFILES)

    def test_mode_schedules_are_not_all_identical(self):
        assert len({(p.mode, p.mode_dwell_s) for p in ALL_PROFILES}) >= 3


# ---------------------------------------------------------------------------
# Expression builders
# ---------------------------------------------------------------------------
class TestExpressionBuilders:
    def test_mode_index_locks_and_cycles(self):
        fire = gp.Profile("F", "x", [(0.0, 1.0, 1.0), (1.0, 0.0, 1.0)],
                          (1.0, 0.1, 0.9), mode="fire")
        light = gp.Profile("L", "x", [(0.0, 1.0, 1.0), (1.0, 0.0, 1.0)],
                           (1.0, 0.1, 0.9), mode="lightning")
        cycle = gp.Profile("C", "x", [(0.0, 1.0, 1.0), (1.0, 0.0, 1.0)],
                           (1.0, 0.1, 0.9), mode="cycle", mode_dwell_s=10.0)
        assert gp.mode_index_expr(fire) == "0"
        assert gp.mode_index_expr(light) == "1"
        assert eval_expr(gp.mode_index_expr(cycle)) in (0, 1)

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    def test_every_emitted_expression_evaluates(self, profile):
        """A syntax error here would surface as a silent dead parameter at the rig."""
        plan = gp.profile_plan(profile)
        for node, pars in plan.items():
            for par, value in pars.items():
                if par in ("text", "rows") or not isinstance(value, str):
                    continue
                eval_expr(value)  # raises on malformed expressions

    @pytest.mark.parametrize("profile", ALL_PROFILES, ids=PROFILE_IDS)
    def test_palette_engine_code_compiles(self, profile):
        compile(gp.palette_engine_code(profile), "<engine>", "exec")

    def test_palette_rows_wrap_to_the_first_anchor(self):
        profile = gp.PROFILES["UV_RAVE"]
        rows = gp.palette_rows(profile)
        assert len(rows) == len(profile.palette)
        assert all(len(r) == 6 for r in rows)
        # last row's secondary must be the first anchor, so the sweep loops
        assert [float(v) for v in rows[-1][3:]] == list(profile.palette[0])

    def test_shake_scales_with_configured_pixels(self):
        small = gp.PROFILES["MONO_PULSE"]   # 2 px
        large = gp.PROFILES["STROBE_ACID"]  # 14 px
        assert abs(eval_expr(gp.shake_expr(large, 0), snare=1.0)) > abs(
            eval_expr(gp.shake_expr(small, 0), snare=1.0)
        )

    def test_silence_leaves_effects_at_their_baseline(self):
        """With no audio the look must be stable, not collapsed to zero."""
        profile = gp.PROFILES["UV_RAVE"]
        assert eval_expr(gp.outline_bright_expr(profile), kick=0.0) == pytest.approx(
            profile.outline_base_bright
        )
        assert eval_expr(gp.zoom_expr(profile), kick=0.0) == pytest.approx(1.0)
        assert eval_expr(gp.kick_flash_expr(profile), kick=0.0) == pytest.approx(1.0)
        assert eval_expr(gp.shake_expr(profile, 0), snare=0.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Behaviour outside TouchDesigner
# ---------------------------------------------------------------------------
class TestUvRaveMirrorsTheShippedLook:
    """UV_RAVE must reproduce what td_startup_hooks._apply_rave_look() applies.

    This is what makes the whole system safe to run at a show: revert_profile()
    is only a real escape hatch if the default profile is byte-for-byte the look
    the rig already boots into. These tests read the live startup hook and
    compare, so drift between the two files is caught here rather than on stage.

    If the startup hook's look is intentionally changed, UV_RAVE must be updated
    to match -- that is the point of the failure, not an annoyance.
    """

    HOOKS = (
        Path(__file__).parent.parent
        / "touchdesigner" / "scripts" / "td_startup_hooks.py"
    ).read_text()

    @staticmethod
    def _norm(expr):
        """Strip whitespace and quotes so source-level differences don't matter.

        Quotes go too because the hook writes long expressions as implicitly
        concatenated literals split across source lines:

            og.par.size.expr = (
                "12 + min(op('fx_kick_env')['bass']*40 + "
                "op('fx_snare_env')['high']*15, 40)"
            )

        Reading that as raw text leaves a ``"`` seam mid-expression. Removing
        whitespace and quotes from BOTH sides compares the thing we care about
        -- operator names, gains, and the min() clamp -- without being fooled by
        how the literal happens to be wrapped.
        """
        return "".join(str(expr).split()).replace('"', "").replace("'", "")

    def test_uv_rave_is_the_default(self):
        assert gp.DEFAULT_PROFILE == "UV_RAVE"

    def test_glow_expression_matches_the_live_clamped_form(self):
        """The clamp is the live-proven half of the freeze fix."""
        live = "12 + min(op('fx_kick_env')['bass']*40 + op('fx_snare_env')['high']*15, 40)"
        assert self._norm(live) in self._norm(self.HOOKS), (
            "the startup hook no longer contains the glow expression this test "
            "pins; re-read td_startup_hooks._apply_glow_transient()"
        )
        ours = gp.glow_size_expr(gp.PROFILES["UV_RAVE"])
        assert self._norm(ours) == self._norm(live)

    def test_outline_brightness_matches_live(self):
        live = "2.5 + op('fx_kick_env')['bass'] * 6"
        assert self._norm(live) in self._norm(self.HOOKS)
        assert self._norm(gp.outline_bright_expr(gp.PROFILES["UV_RAVE"])) == self._norm(live)

    def test_kick_flash_matches_live(self):
        live = "1 + op('fx_kick_env')['bass'] * 8"
        assert self._norm(live) in self._norm(self.HOOKS)
        assert self._norm(gp.kick_flash_expr(gp.PROFILES["UV_RAVE"])) == self._norm(live)

    def test_zoom_matches_live(self):
        live = "1 + op('fx_kick_env')['bass'] * 0.25"
        assert self._norm(live) in self._norm(self.HOOKS)
        assert self._norm(gp.zoom_expr(gp.PROFILES["UV_RAVE"])) == self._norm(live)

    def test_palette_anchors_match_the_live_rave_palette(self):
        """The five neon anchors the rave look pass writes into fx_palette_table."""
        for rgb in gp.PROFILES["UV_RAVE"].palette:
            as_written = "(%s, %s, %s)" % rgb
            # the hook writes them as tuples like (0.0, 1.0, 1.0)
            assert self._norm(as_written) in self._norm(self.HOOKS), (
                "UV_RAVE anchor %s is not in the live rave palette" % (rgb,)
            )

    def test_fire_tint_matches_live(self):
        tint = gp.PROFILES["UV_RAVE"].fire_tint
        assert tint == (1.0, 0.1, 0.9)
        for channel, value in zip("rgb", tint):
            assert self._norm("color%s = %s" % (channel, value)) in self._norm(self.HOOKS)

    def test_mono_saturation_matches_live(self):
        assert gp.PROFILES["UV_RAVE"].mono_saturation == 0.12
        assert self._norm("saturationmult = 0.12") in self._norm(self.HOOKS)

    def test_mode_cycle_matches_live_dwell(self):
        live = "int(absTime.seconds / 30.0) % 2"
        assert self._norm(live) in self._norm(self.HOOKS)
        ours = gp.mode_index_expr(gp.PROFILES["UV_RAVE"])
        assert eval_expr(ours) == eval_expr(live)

    def test_uv_rave_trails_differ_only_by_the_additive_energy_term(self):
        """The one intentional divergence: energy term plus the runaway clamp."""
        assert self._norm("0.890000 - op('fx_lfo_decay')['chan1'] * 0.03") in self._norm(
            self.HOOKS
        )
        ours = gp.trail_valuemult_expr(gp.PROFILES["UV_RAVE"])
        assert "0.89 - op('fx_lfo_decay')['chan1'] * 0.03" in ours
        assert "fx_master" in ours and "min(" in ours
        # and in a silent room it must land on the live value
        assert eval_expr(ours, energy=1.0, lfo_decay=0.0) == pytest.approx(0.89)


class TestOutsideTouchDesigner:
    def test_apply_is_a_safe_no_op_without_td(self):
        result = gp.apply_profile("UV_RAVE")
        assert result["applied"] is False
        assert any("no TD context" in line for line in result["report"])

    def test_unknown_profile_never_raises(self):
        result = gp.apply_profile("NOPE_NOT_REAL")
        assert result["applied"] is False

    def test_selected_profile_always_returns_a_real_profile(self):
        assert gp.selected_profile() in gp.PROFILES

    def test_in_td_detects_an_injected_op_global(self):
        """The TD-detection must not silently no-op at the rig.

        ``__builtins__`` is a module in __main__ but a dict in an imported
        module, so a membership test would answer "not in TD" while running in
        TD. Simulate TD by injecting ``op`` the way TD does and assert both
        directions.
        """
        import builtins

        assert gp._in_td() is False
        builtins.op = lambda path: None
        try:
            assert gp._in_td() is True
        finally:
            del builtins.op
        assert gp._in_td() is False

    def test_profile_plan_covers_the_live_node_contract(self):
        """These names are fixed by extend_dj_graphics.py and the startup hook."""
        expected = {
            "fx_palette_table", "fx_palette_engine_cb", "fx_palette_mono",
            "outline_level", "outline_glow", "fx_kick_bright", "fx_kick_expand",
            "fx_snare_shake", "fx_trail_hsv", "fire_tint", "visual_switch",
        }
        assert expected <= set(gp.profile_plan(gp.PROFILES["UV_RAVE"]))
