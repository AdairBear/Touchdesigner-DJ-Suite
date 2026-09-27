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

import copy
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


# ===========================================================================
# §8 slice: per-profile flame floor, bus refusal, bus/installer behaviour
# ===========================================================================
EXTEND = SCRIPTS / "extend_dj_graphics.py"

# The fx_audio_bands callback baked into DJ_Graphics_LIVE.toe, read out of the
# template copy with toeexpand on 2026-09-27. The rebuild's FFT callback must
# produce exactly these numbers or UV_RAVE's kick/snare triggers shift.
LIVE_BANDS_CB = '''
def onCook(scriptOp):
    scriptOp.clear()
    src = op('audio_spectrum')
    bass = 0.0
    high = 0.0
    if src is not None and src.numChans > 0 and src.numSamples > 0:
        ch = src[0]
        n = src.numSamples
        try:
            vals = ch.vals
            khi = min(2, n - 1)
            slo = min(3, n - 1)
            shi = min(40, n - 1)
            bass = sum(abs(v) for v in vals[0:khi + 1]) / max(1, khi + 1)
            high = sum(abs(v) for v in vals[slo:shi + 1]) / max(1, shi - slo + 1)
        except Exception:
            pass
    scriptOp.appendChan('bass').vals = [bass]
    scriptOp.appendChan('high').vals = [high]
    return
'''


class _Chan:
    def __init__(self, vals):
        self.vals = list(vals)

    def eval(self):
        return self.vals[0]


class _Chop:
    """Minimal CHOP: named single-sample channels, or one multi-sample channel."""

    def __init__(self, chans=None, samples=None):
        self._chans = {k: _Chan([v]) for k, v in (chans or {}).items()}
        self._samples = samples
        self.numChans = 1 if samples is not None else len(self._chans)
        self.numSamples = len(samples) if samples is not None else 1

    def __getitem__(self, key):
        if isinstance(key, int):
            return _Chan(self._samples)
        return self._chans.get(key)


class _ScriptOp:
    def __init__(self):
        self.out = {}

    def clear(self):
        self.out = {}

    def appendChan(self, name):
        chan = _Chan([])
        self.out[name] = chan
        return chan


class _Root:
    def findChildren(self, **_kw):
        return []


def load_extend():
    """Exec extend_dj_graphics.py with TD stubbed and its auto-build disabled."""
    ns = {"EXTEND_NO_AUTORUN": True, "op": lambda _p: None, "root": _Root(),
          "COMP": object, "__name__": "extend_under_test"}
    exec(compile(EXTEND.read_text(), str(EXTEND), "exec"), ns)
    return ns


def run_callback(code, world):
    """Exec a Script CHOP callback against a fake op() and return its channels."""
    ns = {"op": lambda name: world.get(name)}
    exec(code, ns)
    sop = _ScriptOp()
    ns["onCook"](sop)
    return {k: c.vals[0] for k, c in sop.out.items()}, ns


def test_importing_extend_with_the_flag_does_not_build():
    ns = load_extend()
    assert "install_react_bus" in ns and "uninstall_react_bus" in ns


@pytest.mark.parametrize("n_bins", [1, 3, 20, 64, 512])
def test_fft_bands_match_the_live_toe_callback_exactly(n_bins):
    ns = load_extend()
    assert ns["USE_REAL_FFT_BANDS"] is True
    spectrum = [((i * 37) % 11 - 5) * 0.013 for i in range(n_bins)]
    world = {"audio_spectrum": _Chop(samples=spectrum)}
    rebuilt, _ = run_callback(ns["AUDIO_BANDS_CODE"], world)
    live, _ = run_callback(LIVE_BANDS_CB, world)
    assert rebuilt == live  # same channels, same values, bit-for-bit


def _bus_world(raw_energy, spectrum=None):
    return {
        "fx_kick_env": _Chop({"bass": 0.4}),
        "fx_snare_env": _Chop({"high": 0.3}),
        "fx_kick_gate": _Chop({"bass": 1.0}),
        "fx_snare_gate": _Chop({"high": 0.0}),
        "fx_audio_bands": _Chop({"bass": 0.2, "high": 0.1}),
        "fx_master": _Chop({"bass": 1.1}),
        "fx_energy_fast": _Chop({"bass": raw_energy}),
        "audio_spectrum": _Chop(samples=spectrum or [0.0] * 3 + [0.5] * 10 + [0.0] * 50),
    }


def test_react_bus_publishes_the_full_vocabulary_in_order():
    ns = load_extend()
    out, _ = run_callback(ns["REACT_BUS_CODE"], _bus_world(0.01))
    assert tuple(out) == ns["REACT_CHANNELS"]
    assert out["kick_gate"] == 1.0 and out["snare_gate"] == 0.0
    assert out["kick"] == 0.4 and out["energy_slow"] == 1.1
    assert out["mid"] == pytest.approx(0.5)  # bins 3..12 of the spectrum


def test_energy_fast_is_normalized_so_a_quiet_feed_still_spans_0_to_1():
    """The 1824c feed is ~1e-4..0.3 raw; an absolute threshold would never fire."""
    ns = load_extend()
    code = ns["REACT_BUS_CODE"]
    cb_ns = {}
    exec(code, cb_ns)
    seen = []
    for raw in (0.002, 0.004, 0.001, 0.004):  # quiet but moving
        world = _bus_world(raw)
        cb_ns["op"] = lambda name, w=world: w.get(name)
        sop = _ScriptOp()
        cb_ns["onCook"](sop)
        seen.append((sop.out["energy_fast"].vals[0], sop.out["drama"].vals[0]))
    values = [v for v, _ in seen]
    assert max(values) == pytest.approx(1.0)       # the loudest recent frame
    assert min(values) < 0.3                        # quiet frames read low
    assert [d for _, d in seen] == [1.0, 1.0, 0.0, 1.0]


def test_react_bus_degrades_to_zero_when_nodes_are_missing():
    ns = load_extend()
    out, _ = run_callback(ns["REACT_BUS_CODE"], {})
    assert set(out.values()) == {0.0}


def test_install_react_bus_only_builds_bus_nodes(monkeypatch):
    """The live-rig installer must never rewrite the UV_RAVE chain."""
    ns = load_extend()
    calls = []

    class _P:
        def op(self, name):
            return object()

    class _React:
        def chans(self):
            return [type("C", (), {"name": n})() for n in ns["REACT_CHANNELS"]]

    ns["P"] = _P()
    for fn in ("wire_audio_bands", "wire_evolution", "wire_palette", "wire_trails",
               "wire_kick", "wire_snare", "build_effects"):
        ns[fn] = lambda *a, _fn=fn, **k: (_ for _ in ()).throw(
            AssertionError("install_react_bus called " + _fn))
    ns["wire_energy_fast"] = lambda bands: calls.append("energy_fast")
    ns["wire_gates"] = lambda: calls.append("gates")
    ns["wire_react_bus"] = lambda: (calls.append("react"), _React())[1]
    result = ns["install_react_bus"]()
    assert result["ok"] is True
    assert calls == ["energy_fast", "gates", "react"]


def test_install_react_bus_aborts_without_the_base_chain():
    ns = load_extend()

    class _Empty:
        def op(self, name):
            return None

    ns["P"] = _Empty()
    result = ns["install_react_bus"]()
    assert result["ok"] is False and "fx_kick_env" in result["missing"]


def test_bus_nodes_never_include_anything_uv_rave_binds():
    ns = load_extend()
    owned = set(ns["REACT_BUS_NODES"])
    assert not owned & {"fx_audio_bands", "fx_audio_bands_cb", "fx_kick_env",
                        "fx_snare_env", "fx_kick_sel", "fx_snare_sel",
                        "fx_energy", "fx_master"}


def test_glitch_lowers_the_flame_floor_and_shipped_looks_do_not():
    assert gp.PROFILES["GLITCH"].react_floor == pytest.approx(0.05)
    for name in SHIPPED:
        assert gp.PROFILES[name].react_floor is None, name


@pytest.mark.parametrize("floor", [-0.01, 1.01, 5.0])
def test_react_floor_out_of_range_is_invalid(floor):
    prof = copy.copy(gp.PROFILES["GLITCH"])
    prof.react_floor = floor
    assert any("react_floor" in p for p in gp.validate_profile(prof))


def test_apply_profile_refuses_a_bus_profile_when_the_bus_is_absent(monkeypatch):
    monkeypatch.setattr(gp, "_in_td", lambda: True)
    monkeypatch.setattr(gp, "_resolve", lambda name: None)
    result = gp.apply_profile("GLITCH")
    assert result["applied"] is False
    assert any("fx_react absent" in line for line in result["report"])
