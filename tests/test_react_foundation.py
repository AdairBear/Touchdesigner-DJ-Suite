"""Offline tests for the reactivity foundation (fx_react bus) and the GLITCH look.

These prove, on a laptop with no TouchDesigner and no audio, the three things
the §8 build promised:

  1. NO REGRESSION. Every shipped profile emits expressions that never reference
     the new fx_react bus, so its plan is byte-identical to the pre-bus rig.
     (The exact-string pins for UV_RAVE live in test_dj_graphics_profiles.py;
     running that suite is the other half of the regression gate.)
  2. GLITCH IS VALID AND BINDS THE GATES. It passes the same schema every look
     passes, and its reactive params reference the discrete fx_react gates.
  3. THE CLAMPS STILL HOLD. Even with every gate and envelope pinned at 1.0,
     GLITCH's glow, flash and trail expressions stay under their hard caps, so a
     low-inertia look cannot freeze or white out the frame.

Run:  ./venv/bin/python -m pytest tests/test_react_foundation.py -v
"""

import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).parent.parent / "touchdesigner" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import dj_graphics_profiles as gp  # noqa: E402

# Reuse the proven fake-TD harness rather than reimplementing it.
sys.path.insert(0, str(Path(__file__).parent))
from test_dj_graphics_profiles import FakeCHOP  # noqa: E402


def make_op_with_react(kick=1.0, snare=1.0, energy=1.5, lfo_decay=0.0, noise=1.0,
                       kick_gate=1.0, snare_gate=1.0, energy_fast=1.0, drama=1.0):
    """Fake ``op()`` that also resolves the fx_react bus channels.

    Defaults are worst case for the clamps: every envelope, gate and drama flag
    pinned on, energy at the top of its range.
    """
    world = {
        "fx_kick_env": FakeCHOP({"bass": kick}),
        "fx_snare_env": FakeCHOP({"high": snare}),
        "fx_master": FakeCHOP({"bass": energy}),
        "fx_lfo_decay": FakeCHOP({"chan1": lfo_decay}),
        "fx_noise": FakeCHOP({"chan1": noise, "chan2": noise}, [noise, noise]),
        "fx_palette_engine": FakeCHOP({"primaryR": 0.5, "primaryG": 0.5,
                                       "primaryB": 0.5}),
        "attr_dj": FakeCHOP({name: 0.0 for name in gp.ae.DJ_CHANNELS}),
        "fx_react": FakeCHOP({
            "kick": kick, "snare": snare,
            "kick_gate": kick_gate, "snare_gate": snare_gate,
            "bass": 1.0, "mid": 1.0, "high": 1.0,
            "energy_slow": energy, "energy_fast": energy_fast, "drama": drama,
        }),
    }
    return lambda path: world.get(path)


SHIPPED = [name for name in gp.PROFILES if name != "GLITCH"]


@pytest.mark.parametrize("name", SHIPPED)
def test_shipped_profiles_never_reference_the_bus(name):
    """No shipped look may reference fx_react -- proves byte-identical to pre-bus."""
    prof = gp.PROFILES[name]
    for audience in (False, True):
        plan = gp.profile_plan(prof, with_energy=True, audience=audience)
        blob = repr(plan)
        assert "fx_react" not in blob, (
            "%s references the fx_react bus (audience=%s); shipped looks must not"
            % (name, audience)
        )


def test_glitch_is_registered_and_valid():
    assert "GLITCH" in gp.PROFILES
    problems = gp.validate_profile(gp.PROFILES["GLITCH"])
    assert problems == [], "GLITCH failed validation: %r" % problems


def test_glitch_declares_low_inertia_and_needs_the_bus():
    g = gp.PROFILES["GLITCH"]
    assert g.inertia == "low"
    assert g.needs_react_bus is True


def test_glitch_binds_the_discrete_gates():
    """GLITCH's reactive params must actually read the gate/drama channels."""
    plan = gp.profile_plan(gp.PROFILES["GLITCH"], audience=False)
    flash = plan["fx_kick_bright"]["brightness1"]
    outline = plan["outline_level"]["brightness1"]
    glow = plan["outline_glow"]["size"]
    assert "fx_react" in flash and "kick_gate" in flash and "drama" in flash
    assert "kick_gate" in outline
    assert "snare_gate" in glow


def test_glitch_clamps_hold_under_worst_case():
    """Every gate + envelope pinned at 1.0 must still respect the hard caps."""
    g = gp.PROFILES["GLITCH"]
    op = make_op_with_react()  # everything pinned on

    glow = eval(gp.glow_size_expr(g, audience=False), {"op": op})
    assert glow <= gp.GLOW_SIZE_HARD_CAP, "glow %.3f exceeds cap" % glow

    flash = eval(gp.kick_flash_expr(g, audience=False), {"op": op})
    assert flash <= gp.KICK_FLASH_HARD_CAP, "flash %.3f exceeds cap" % flash

    trail = eval(gp.trail_valuemult_expr(g, with_energy=True, audience=False),
                 {"op": op})
    assert trail < 1.0, "trail %.3f would run away" % trail
    assert trail <= gp.TRAIL_VALUEMULT_HARD_CAP


def test_glitch_flash_actually_bigger_than_baseline_on_a_hit():
    """The gates must add punch: GLITCH flash on a hit exceeds its own no-gate base."""
    g = gp.PROFILES["GLITCH"]
    op = make_op_with_react()
    flash = eval(gp.kick_flash_expr(g, audience=False), {"op": op})
    baseline = 1.0 + 1.0 * g.kick_flash_gain  # kick env only, no gate/drama
    assert flash > baseline, "gates added no punch (%.3f <= %.3f)" % (flash, baseline)


def test_high_inertia_with_gate_is_a_contradiction():
    """The validator must reject a high-inertia look that binds a per-hit gate."""
    bad = gp.Profile(
        name="BAD", description="high inertia but strobing",
        palette=[gp.CYAN, gp.MAGENTA], fire_tint=gp.CYAN,
        inertia="high", kick_gate_gain=5.0, needs_react_bus=True,
    )
    problems = gp.validate_profile(bad)
    assert any("contradiction" in p for p in problems), problems


@pytest.mark.parametrize("name", list(gp.PROFILES))
def test_every_profile_including_glitch_validates(name):
    assert gp.validate_profile(gp.PROFILES[name]) == []
