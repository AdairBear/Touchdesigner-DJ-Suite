"""Offline unit tests for the in-TD verification probe (verify_network_v2.py).

The probe must be importable and fully exercisable OUTSIDE TouchDesigner: all TD
globals are reached through a TDContext, so these tests inject a fake ``op()``
world (dict-backed FakeOps with a ``.par`` namespace) and assert the PASS/FAIL/
WARN logic without a running TD.

Covers the PLAN-01 acceptance cases:
  * all-good network -> PASS
  * a missing op -> ops_exist FAILs while the other checks still run
  * a 1-indexed uniname layout -> glsl_bindings FAIL naming the off-by-one
  * a BlackHole audio device -> WARN (not FAIL)
  * report JSON schema stable (context, timestamp, checks[], result)
  * a check that raises is isolated (ERROR) and never aborts the probe
  * two-paste live-uniform flow: phase 1 PENDING, phase 2 deltas
"""

import json
import sys
from pathlib import Path

# The probe lives under touchdesigner/scripts (not python/, which conftest adds).
SCRIPTS = Path(__file__).parent.parent / "touchdesigner" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import verify_network_v2 as v  # noqa: E402


# ---------------------------------------------------------------------------
# Fake TD op world
# ---------------------------------------------------------------------------
class FakePar:
    def __init__(self, value):
        self._value = value

    def eval(self):
        return self._value

    @property
    def val(self):
        return self._value

    @property
    def name(self):  # only used by the syphon name-par scan
        return getattr(self, "_name", "")


class FakeParNamespace:
    def __init__(self, pars):
        # pars: {par_name: value}
        self._pars = {name: FakePar(val) for name, val in pars.items()}
        for p_name, p in self._pars.items():
            p._name = p_name

    def __getattr__(self, name):
        pars = self.__dict__.get("_pars", {})
        if name in pars:
            return pars[name]
        raise AttributeError(name)


class FakeOp:
    def __init__(self, name, pars=None, inputs=None, mask_peak=None):
        self.name = name
        self.par = FakeParNamespace(pars or {})
        self.inputs = inputs or []
        self._mask_peak = mask_peak
        self.storage = {}

    def pars(self):
        return list(self.par._pars.values())

    def numpyArray(self, delayed=False):
        if self._mask_peak is None:
            raise ValueError("no pixels")
        import numpy as np

        return np.array([[0.0, self._mask_peak]], dtype="float32")


class FakeProject:
    def __init__(self, cook_rate=60.0):
        self.cookRate = cook_rate


def _glsl_pars(names, values):
    pars = {}
    for i in range(10):
        pars["uniname" + str(i)] = names[i]
        pars["value" + str(i) + "x"] = values[i]
    return pars


def build_world(
    uniform_names=None,
    uniform_values=None,
    audio_device="PreSonus Studio 1824c",
    osc_port=7000,
    osc_active=True,
    syphon_active=True,
    syphon_sender="TDSyphonSpoutOut",
    mask_peak=0.9,
    drop=(),
    ghosts=(),
):
    """Build a dict-backed op world. Returns (op_func, nodes)."""
    names = uniform_names or list(v.CANONICAL_UNIFORMS)
    values = uniform_values or [0.0] * 10
    nodes = {}

    def add(name, pars=None, inputs=None, mask_peak=None):
        nodes[name] = FakeOp(name, pars=pars, inputs=inputs, mask_peak=mask_peak)
        return nodes[name]

    body = add("body_mask_top", mask_peak=mask_peak)
    edge = add("edge_detect", inputs=[body])
    edge_blur = add("edge_blur", inputs=[edge])
    zero_src = add("zero_src")
    fire = add(
        "fire_aura_glsl",
        pars=_glsl_pars(names, values),
        inputs=[edge_blur, zero_src, zero_src],
    )
    light = add(
        "lightning_glsl",
        pars=_glsl_pars(names, values),
        inputs=[edge_blur, zero_src, zero_src],
    )
    switch = add("visual_switch", inputs=[fire, light])
    bloom_blur = add("bloom_blur", inputs=[switch])
    bloom_post = add("bloom_post", inputs=[switch, bloom_blur])
    final = add("final_composite", inputs=[bloom_post])
    add(
        "syphonOut1",
        pars={"active": syphon_active, "sendername": syphon_sender},
        inputs=[final],
    )
    add("oscin1", pars={"port": osc_port, "active": osc_active})
    audio_in = add("audio_in", pars={"device": audio_device})
    add("audio_spectrum", inputs=[audio_in])
    add("aura_compositor")
    add("segmentation_mask_reader")

    for name in ghosts:
        add(name)
    for name in drop:
        nodes.pop(name, None)

    def op_func(path):
        leaf = path.rsplit("/", 1)[-1]
        return nodes.get(leaf)

    return op_func, nodes


def make_ctx(op_func, now=100.0, storage=None, context="initial", project=None):
    return v.TDContext(
        op=op_func,
        project=project or FakeProject(),
        now=(lambda: now),
        storage=storage if storage is not None else {},
        context=context,
    )


def _by_name(report, check_name):
    return [c for c in report["checks"] if c["check"] == check_name]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def test_all_good_network_passes():
    op_func, _ = build_world()
    report = v.run_checks(make_ctx(op_func))
    # uniforms_alive is PENDING on the first paste; that is not a FAIL.
    assert report["result"] == "PASS", report["failed"] + report["errored"]
    assert _by_name(report, "ops_exist")[0]["status"] == v.PASS
    assert _by_name(report, "wiring")[0]["status"] == v.PASS
    assert _by_name(report, "glsl_bindings:fire_aura_glsl")[0]["status"] == v.PASS
    assert _by_name(report, "glsl_bindings:lightning_glsl")[0]["status"] == v.PASS
    assert _by_name(report, "osc")[0]["status"] == v.PASS
    assert _by_name(report, "syphon")[0]["status"] == v.PASS


def test_missing_op_fails_that_check_others_still_run():
    op_func, _ = build_world(drop=("bloom_post",))
    report = v.run_checks(make_ctx(op_func))
    ops = _by_name(report, "ops_exist")[0]
    assert ops["status"] == v.FAIL
    assert "bloom_post" in ops["missing"]
    # Other independent checks still executed and passed.
    assert _by_name(report, "osc")[0]["status"] == v.PASS
    assert _by_name(report, "glsl_bindings:fire_aura_glsl")[0]["status"] == v.PASS
    assert report["result"] == "FAIL"


def test_off_by_one_uniname_fails_with_named_diagnosis():
    # 1-indexed write: uniname0 empty, canonical names shifted up one slot.
    shifted = [""] + list(v.CANONICAL_UNIFORMS[:9])
    op_func, _ = build_world(uniform_names=shifted)
    report = v.run_checks(make_ctx(op_func))
    fire = _by_name(report, "glsl_bindings:fire_aura_glsl")[0]
    assert fire["status"] == v.FAIL
    assert "OFF-BY-ONE" in fire["detail"]
    assert "uniname0" in fire["detail"]
    assert report["result"] == "FAIL"


def test_blackhole_device_warns_not_fails():
    op_func, _ = build_world(audio_device="BlackHole 2ch")
    report = v.run_checks(make_ctx(op_func))
    audio = _by_name(report, "audio_device")[0]
    assert audio["status"] == v.WARN
    assert "BlackHole" in audio["detail"] or "bass=0.0001" in audio["detail"]
    # A WARN must not flip the overall result to FAIL.
    assert report["result"] == "PASS"


def test_1824c_device_passes():
    op_func, _ = build_world(audio_device="PreSonus Studio 1824c")
    report = v.run_checks(make_ctx(op_func))
    assert _by_name(report, "audio_device")[0]["status"] == v.PASS


def test_wiring_mismatch_fails():
    op_func, nodes = build_world()
    # Break the fire GLSL input chain (swap input 0 to zero_src).
    nodes["fire_aura_glsl"].inputs = [
        nodes["zero_src"],
        nodes["zero_src"],
        nodes["zero_src"],
    ]
    report = v.run_checks(make_ctx(op_func))
    wiring = _by_name(report, "wiring")[0]
    assert wiring["status"] == v.FAIL
    assert "fire_aura_glsl" in wiring["detail"]


def test_osc_wrong_port_fails():
    op_func, _ = build_world(osc_port=9000)
    report = v.run_checks(make_ctx(op_func))
    osc = _by_name(report, "osc")[0]
    assert osc["status"] == v.FAIL
    assert "9000" in osc["detail"]


def test_syphon_wrong_sender_fails():
    op_func, _ = build_world(syphon_sender="SomethingElse")
    report = v.run_checks(make_ctx(op_func))
    syphon = _by_name(report, "syphon")[0]
    assert syphon["status"] == v.FAIL


def test_syphon_missing_name_par_reports_info():
    op_func, nodes = build_world()
    # Simulate a TD build with no 'sendername' par (and no 'name'-ish pars).
    nodes["syphonOut1"] = FakeOp("syphonOut1", pars={"active": True, "sendertag": "x"})
    report = v.run_checks(make_ctx(op_func))
    syphon = _by_name(report, "syphon")[0]
    assert syphon["status"] == v.INFO


def test_mask_black_warns():
    op_func, _ = build_world(mask_peak=0.0)
    report = v.run_checks(make_ctx(op_func))
    mask = _by_name(report, "mask_alive")[0]
    assert mask["status"] == v.WARN
    assert "BLACK" in mask["detail"]
    assert report["result"] == "PASS"  # WARN does not fail the run


def test_mask_alive_passes_when_non_black():
    op_func, _ = build_world(mask_peak=0.7)
    report = v.run_checks(make_ctx(op_func))
    assert _by_name(report, "mask_alive")[0]["status"] == v.PASS


def test_v1_ghost_ops_reported_as_info_not_fail():
    op_func, _ = build_world(ghosts=("noise_embers", "camera_in"))
    report = v.run_checks(make_ctx(op_func))
    ops = _by_name(report, "ops_exist")[0]
    assert ops["status"] == v.PASS
    assert "noise_embers" in ops["v1_ghosts_present"]
    assert "INFO stale v1 ghost" in ops["detail"]


def test_broken_check_is_isolated_as_error():
    op_func, _ = build_world()

    def exploding(ctx, base):
        raise RuntimeError("boom")

    original = list(v._CHECKS)
    try:
        v._CHECKS.insert(0, exploding)
        report = v.run_checks(make_ctx(op_func))
    finally:
        v._CHECKS[:] = original
    errored = [c for c in report["checks"] if c["status"] == v.ERROR]
    assert any("boom" in c["detail"] for c in errored)
    # The rest of the suite still ran.
    assert _by_name(report, "osc")[0]["status"] == v.PASS
    assert report["result"] == "FAIL"


def test_report_schema_stable():
    op_func, _ = build_world()
    report = v.run_checks(make_ctx(op_func))
    for key in ("context", "timestamp", "checks", "result", "failed", "errored"):
        assert key in report
    assert isinstance(report["checks"], list)
    for c in report["checks"]:
        assert "check" in c and "status" in c and "detail" in c
    # Must be JSON-serializable (this is the agent-facing channel).
    json.dumps(report)


def test_context_label_recorded():
    op_func, _ = build_world()
    report = v.run_checks(make_ctx(op_func, context="post_reload"))
    assert report["context"] == "post_reload"


def test_uniforms_alive_two_phase_flow():
    op_func, nodes = build_world(uniform_values=[0.1] * 10)
    storage = {}

    # Phase 1: no snapshot yet -> PENDING, snapshot stored.
    r1 = v.run_checks(make_ctx(op_func, now=100.0, storage=storage))
    u1 = _by_name(r1, "uniforms_alive")[0]
    assert u1["status"] == v.PENDING
    assert v.SNAP_KEY in storage

    # Move audio slots 4-8, then phase 2 well past the min gap.
    fire = nodes["fire_aura_glsl"]
    for i in range(4, 9):
        fire.par._pars["value" + str(i) + "x"] = FakePar(0.5)
    r2 = v.run_checks(make_ctx(op_func, now=110.0, storage=storage))
    u2 = _by_name(r2, "uniforms_alive")[0]
    assert u2["status"] == v.PASS
    assert u2["audio_slots_moved"] >= 5
    assert v.SNAP_KEY not in storage  # snapshot consumed


def test_uniforms_alive_phase2_silence_warns_not_fails():
    op_func, _ = build_world(uniform_values=[0.1] * 10)
    storage = {}
    v.run_checks(make_ctx(op_func, now=100.0, storage=storage))  # phase 1
    # No values changed (silence). Phase 2 past the gap.
    report = v.run_checks(make_ctx(op_func, now=120.0, storage=storage))
    u2 = _by_name(report, "uniforms_alive")[0]
    assert u2["status"] == v.WARN
    assert report["result"] == "PASS"  # silence is not a failure


def test_uniforms_alive_second_paste_too_soon_stays_pending():
    op_func, _ = build_world()
    storage = {}
    v.run_checks(make_ctx(op_func, now=100.0, storage=storage))  # phase 1
    report = v.run_checks(make_ctx(op_func, now=101.0, storage=storage))  # 1s later
    u2 = _by_name(report, "uniforms_alive")[0]
    assert u2["status"] == v.PENDING
    assert v.SNAP_KEY in storage  # snapshot preserved for a real 2nd paste


def test_format_table_and_write_report(tmp_path):
    op_func, _ = build_world()
    report = v.run_checks(make_ctx(op_func))
    table = v.format_table(report)
    assert "RESULT:" in table
    path = v.write_report(report, logs_dir=str(tmp_path))
    assert Path(path).exists()
    loaded = json.loads(Path(path).read_text())
    assert loaded["result"] == report["result"]
