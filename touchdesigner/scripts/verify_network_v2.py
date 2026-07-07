# verify_network_v2.py — In-TD read-back probe for the v2 network
# ================================================================
# WHY THIS EXISTS (PLAN-01, 2026-07-06)
#   Every past attempt died at the same cliff: the build scripts WRITE into
#   TouchDesigner blind, and the only read-back instrument was Thomas's
#   eyeballs at the desk. That happened once in three months and found three
#   failures the code-side "all green" had missed. This is the missing third
#   channel: a READ-ONLY probe that runs inside TD, measures the actual network
#   state, and writes a machine-readable JSON report an agent can read PLUS a
#   human PASS/FAIL/WARN table to the Textport.
#
#   The Textport is invisible to a future Claude session — the JSON file at
#   logs/verify_report_<timestamp>.json IS the deliverable. Paste the filename
#   into the next session and it can state which desk items passed without
#   asking Thomas anything.
#
# HOW TO USE (inside TouchDesigner)
#   1. Build the network first (build_network_v2.py).
#   2. Open the Textport (Alt+T) and paste:
#        exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/'
#                  'touchdesigner/scripts/verify_network_v2.py').read())
#      It auto-runs verify() on import.
#   3. Post-reload persistence test (the April killer): after Cmd+S -> close ->
#      reopen the .toe, paste:
#        VERIFY_CONTEXT='post_reload'; exec(open('.../verify_network_v2.py').read())
#   4. Live-uniform (music-on) test: paste the plain one-liner TWICE, >=5 s
#      apart. The first paste stores a snapshot; the second computes per-slot
#      deltas and finalizes the uniforms_alive check.
#
# HARD CONSTRAINTS (see PLAN-01)
#   * READ-ONLY. This script must not set a single parameter. A verify that
#     repairs state re-poisons the evidence, exactly like the April hand-patches.
#   * No time.sleep() / no blocking inside TD — the cook loop stalls freeze the
#     UI. Live-uniform motion uses a two-paste snapshot instead.
#   * One broken check must never abort the probe — each runs in its own
#     try/except and records ERROR, then continues. Partial reports are how the
#     false-"system is broken" spiral was avoided.
#   * GLSL Vectors page is 0-INDEXED (uniname0, value0x) and per-component only
#     (par.value0, the group accessor, raises tdError on TD 2022.35320).
#   * stdlib + numpy only (TD's embedded Python has no venv).
#
# This file is importable OUTSIDE TD (for tests/test_verify_network_v2.py): all
# TouchDesigner globals (op, project, absTime, run) are reached through a small
# TDContext indirection, never as bare names inside the check functions. The
# auto-run block at the bottom is the only place real TD globals are touched,
# and it is guarded so a plain `import` never fires it.
# ================================================================

import json
import os

# Must match build_network_v2.py's REPO_ROOT exactly (same machine).
REPO_ROOT = "/Users/thomasadair/projects/touchdesigner-dj-suite"
LOGS_DIR = os.path.join(REPO_ROOT, "logs")

# --- Source of truth: the v2 op set. Copied as a literal (the probe imports
# nothing from the builder) with the builder as the named source. PLAN-04 adds
# the contract test that keeps these two lists in sync. ---
EXPECTED_OPS = [
    "body_mask_top",
    "edge_detect",
    "edge_blur",
    "zero_src",
    "fire_aura_glsl",
    "lightning_glsl",
    "visual_switch",
    "bloom_blur",
    "bloom_post",
    "final_composite",
    "syphonOut1",
    "oscin1",
    "audio_in",
    "audio_spectrum",
    "aura_compositor",
    "segmentation_mask_reader",
]

# v1-era ghosts. Presence under the v2 network means a stale network is loaded;
# reported as INFO (never FAIL) so a stale-network warning never reads as a
# missing-op panic (the June-5 false-"MISSING" spiral).
V1_GHOST_OPS = ["camera_in", "burst_flash", "flame_layers", "noise_embers"]

# TOP-chain wiring, following build_network_v2.py. Each entry:
#   (op_name, [expected .inputs[*].name in order])
EXPECTED_WIRING = [
    ("edge_detect", ["body_mask_top"]),
    ("edge_blur", ["edge_detect"]),
    ("fire_aura_glsl", ["edge_blur", "zero_src", "zero_src"]),
    ("lightning_glsl", ["edge_blur", "zero_src", "zero_src"]),
    ("visual_switch", ["fire_aura_glsl", "lightning_glsl"]),
    ("bloom_blur", ["visual_switch"]),
    ("bloom_post", ["visual_switch", "bloom_blur"]),
    ("final_composite", ["bloom_post"]),
    ("syphonOut1", ["final_composite"]),
    ("audio_spectrum", ["audio_in"]),
]

# Canonical 10-name uniform map, 0-indexed (uniname0..uniname9). Verified
# against build_network_v2.py:UNIFORM_NAMES and aura_compositor.py's per-frame
# value0x..value8x writes (value9x/uTime is time, slot 9).
CANONICAL_UNIFORMS = [
    "uFlameIntensity",  # uniname0 / value0x
    "uTurbulence",  # uniname1 / value1x
    "uDistortion",  # uniname2 / value2x
    "uSparkle",  # uniname3 / value3x
    "uMotionEnergy",  # uniname4 / value4x
    "uBassEnergy",  # uniname5 / value5x
    "uMidEnergy",  # uniname6 / value6x
    "uHighEnergy",  # uniname7 / value7x
    "uBurstDecay",  # uniname8 / value8x
    "uTime",  # uniname9 / value9x  (time slot)
]

GLSL_OPS = ["fire_aura_glsl", "lightning_glsl"]

# Storage key + minimum spacing for the two-paste live-uniform snapshot.
SNAP_KEY = "_verify_snap"
SNAP_MIN_GAP_S = 4.0

# Status constants.
PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
INFO = "INFO"
ERROR = "ERROR"
PENDING = "PENDING"


# ----------------------------------------------------------------------------
# TDContext — the single indirection point for every TouchDesigner global.
# Inside TD it is built from the real globals; in tests a fake is injected.
# ----------------------------------------------------------------------------
class TDContext:
    """Bundles the TD runtime handles the checks need.

    Attributes:
        op: callable(path) -> op-or-None (TD's global ``op``).
        project: TD's global ``project`` (has ``.cookRate``), or None.
        now: callable() -> float monotonic seconds (TD's ``absTime.seconds``).
        storage: a dict-like for cross-paste snapshot state.
        context: label recorded in the report ("initial" / "post_reload").
    """

    def __init__(
        self, op=None, project=None, now=None, storage=None, context="initial"
    ):
        self.op = op or (lambda _path: None)
        self.project = project
        self.now = now or (lambda: 0.0)
        self.storage = storage if storage is not None else {}
        self.context = context


def _par_value(node, par_name):
    """Read a parameter's evaluated value, tolerating .eval()/.val/attr forms.

    Returns None if the parameter does not exist. Never raises for a missing
    par — callers decide whether absence is a FAIL.
    """
    par = getattr(getattr(node, "par", None), par_name, None)
    if par is None:
        return None
    for reader in ("eval", "val"):
        got = getattr(par, reader, None)
        if callable(got):
            return got()
        if got is not None:
            return got
    return par


def _input_names(node):
    """Return [.name for each op in node.inputs], or [] if unavailable."""
    inputs = getattr(node, "inputs", None) or []
    names = []
    for inp in inputs:
        if inp is None:
            continue
        names.append(getattr(inp, "name", None))
    return names


# ----------------------------------------------------------------------------
# Individual checks. Each returns a dict with at least {check, status, detail}.
# None of them mutate TD state.
# ----------------------------------------------------------------------------
def check_ops_exist(ctx, base):
    missing = [name for name in EXPECTED_OPS if ctx.op(base + "/" + name) is None]
    ghosts = [name for name in V1_GHOST_OPS if ctx.op(base + "/" + name) is not None]
    result = {
        "check": "ops_exist",
        "present": len(EXPECTED_OPS) - len(missing),
        "expected": len(EXPECTED_OPS),
        "missing": missing,
        "v1_ghosts_present": ghosts,
    }
    if missing:
        result["status"] = FAIL
        result["detail"] = "missing ops: " + ", ".join(missing)
    else:
        result["status"] = PASS
        result["detail"] = "all %d v2 ops present" % len(EXPECTED_OPS)
    if ghosts:
        # INFO addendum, never a FAIL — a stale network warning must not read
        # as a missing-op panic.
        result["detail"] += " | INFO stale v1 ghost ops present: " + ", ".join(ghosts)
    return result


def check_wiring(ctx, base):
    mismatches = []
    checked = 0
    for op_name, expected_inputs in EXPECTED_WIRING:
        node = ctx.op(base + "/" + op_name)
        if node is None:
            mismatches.append("%s: op missing" % op_name)
            continue
        checked += 1
        actual = _input_names(node)
        if actual != expected_inputs:
            mismatches.append(
                "%s.inputs = %s (expected %s)" % (op_name, actual, expected_inputs)
            )
    result = {"check": "wiring", "edges_checked": checked, "mismatches": mismatches}
    if mismatches:
        result["status"] = FAIL
        result["detail"] = "; ".join(mismatches)
    else:
        result["status"] = PASS
        result["detail"] = "all %d wiring edges correct" % checked
    return result


def _check_one_glsl_bindings(ctx, base, glsl_name):
    node = ctx.op(base + "/" + glsl_name)
    if node is None:
        return {
            "check": "glsl_bindings:" + glsl_name,
            "status": FAIL,
            "detail": "op missing",
            "names": [],
        }
    names = [_par_value(node, "uniname" + str(i)) for i in range(10)]
    names = [("" if n is None else str(n)) for n in names]

    if names == CANONICAL_UNIFORMS:
        return {
            "check": "glsl_bindings:" + glsl_name,
            "status": PASS,
            "detail": "uniname0..9 match canonical map",
            "names": names,
        }

    # Off-by-one detector: the historical killer was 1-indexed writes, which
    # leave uniname0 empty and shift the canonical names up one slot.
    shifted = [""] + CANONICAL_UNIFORMS[:9]
    if names == shifted or (names[0] == "" and names[1] == CANONICAL_UNIFORMS[0]):
        return {
            "check": "glsl_bindings:" + glsl_name,
            "status": FAIL,
            "detail": (
                "OFF-BY-ONE: uniname0 is empty and names start at uniname1 "
                "(1-indexed write). Vectors page is 0-indexed — uniname0 must "
                "be '%s'. This is the exact bug that bound nothing for days."
                % CANONICAL_UNIFORMS[0]
            ),
            "names": names,
        }

    diffs = [
        "uniname%d='%s' (expected '%s')" % (i, names[i], CANONICAL_UNIFORMS[i])
        for i in range(10)
        if names[i] != CANONICAL_UNIFORMS[i]
    ]
    return {
        "check": "glsl_bindings:" + glsl_name,
        "status": FAIL,
        "detail": "; ".join(diffs),
        "names": names,
    }


def check_glsl_bindings(ctx, base):
    return [_check_one_glsl_bindings(ctx, base, name) for name in GLSL_OPS]


def _snapshot_values(ctx, base, glsl_name):
    """Read value0x..value9x per-component (group accessor raises tdError)."""
    node = ctx.op(base + "/" + glsl_name)
    if node is None:
        return None
    vals = []
    for i in range(10):
        raw = _par_value(node, "value" + str(i) + "x")
        try:
            vals.append(float(raw))
        except (TypeError, ValueError):
            vals.append(None)
    return vals


def check_uniforms_alive(ctx, base):
    """Two-paste live-uniform check.

    First paste with no stored snapshot: store value0x..9x + timestamp, return
    PENDING. Second paste >= SNAP_MIN_GAP_S later: compute per-slot deltas,
    clear the snapshot, and report. Slots are reported in two groups so silence
    (no music -> zero audio deltas) is never a false FAIL:
      * audio slots 0-8  — compositor-written, move only with a live signal.
      * time slot 9 (uTime) — moves only if value9x is bound to absTime.seconds;
        on a pure v2 build uTime is shader-driven (built-in iTime) and value9x
        is static, so a zero delta here is INFO, not FAIL.
    """
    current = _snapshot_values(ctx, base, "fire_aura_glsl")
    if current is None:
        return {
            "check": "uniforms_alive",
            "status": ERROR,
            "detail": "fire_aura_glsl missing — cannot snapshot uniforms",
        }

    now = None
    try:
        now = float(ctx.now())
    except (TypeError, ValueError):
        now = None

    stored = ctx.storage.get(SNAP_KEY)
    if not stored:
        ctx.storage[SNAP_KEY] = {"values": current, "t": now}
        return {
            "check": "uniforms_alive",
            "status": PENDING,
            "detail": (
                "phase 1: snapshot stored. Paste the same one-liner again "
                ">=%.0f s from now (play music first to exercise slots 0-8)."
                % SNAP_MIN_GAP_S
            ),
            "phase": 1,
        }

    prev_vals = stored.get("values") or []
    prev_t = stored.get("t")
    gap = None
    if now is not None and prev_t is not None:
        gap = now - prev_t
        if gap < SNAP_MIN_GAP_S:
            # Too soon — keep phase-1 snapshot, tell the user to wait.
            return {
                "check": "uniforms_alive",
                "status": PENDING,
                "detail": (
                    "phase 1 snapshot is only %.1f s old; wait until >=%.0f s "
                    "then paste again." % (gap, SNAP_MIN_GAP_S)
                ),
                "phase": 1,
            }

    ctx.storage.pop(SNAP_KEY, None)  # consume the snapshot

    deltas = []
    for i in range(10):
        a = prev_vals[i] if i < len(prev_vals) else None
        b = current[i] if i < len(current) else None
        if a is None or b is None:
            deltas.append(None)
        else:
            deltas.append(abs(b - a))

    audio_deltas = deltas[0:9]
    audio_moved = [d for d in audio_deltas if d is not None and d > 1e-6]
    time_delta = deltas[9]
    time_moved = time_delta is not None and time_delta > 1e-6

    detail = "phase 2 (gap %s s): audio slots 0-8 moved on %d/9 slots; " % (
        ("%.1f" % gap) if gap is not None else "?",
        len(audio_moved),
    )
    if audio_moved:
        status = PASS
        detail += "compositor is writing live uniforms."
    else:
        status = WARN
        detail += (
            "no audio-slot movement — expected if no music was playing or "
            "aura_compositor is inactive (not a failure). If music WAS playing, "
            "check aura_compositor Active + Frame Start and audio_in device."
        )
    if time_moved:
        detail += " uTime slot 9 moving."
    else:
        detail += (
            " INFO: uTime slot 9 static — normal on a pure v2 build (shader uses "
            "built-in iTime; value9x is bound only if a script set "
            "value9x.expr=absTime.seconds)."
        )

    return {
        "check": "uniforms_alive",
        "status": status,
        "detail": detail,
        "phase": 2,
        "gap_seconds": gap,
        "deltas": deltas,
        "audio_slots_moved": len(audio_moved),
        "time_slot_moved": bool(time_moved),
    }


def check_audio_device(ctx, base):
    node = ctx.op(base + "/audio_in")
    if node is None:
        return {"check": "audio_device", "status": FAIL, "detail": "audio_in missing"}
    device = _par_value(node, "device")
    device_str = "" if device is None else str(device)
    if "1824" in device_str.lower():
        return {
            "check": "audio_device",
            "status": PASS,
            "detail": "device = %r (PreSonus 1824c)" % device_str,
            "device": device_str,
        }
    return {
        "check": "audio_device",
        "status": WARN,
        "detail": (
            "device = %r — not the 1824c. BlackHole/other yields the "
            "bass=0.0001 silent-audio failure mode. Select PreSonus Studio "
            "1824c on audio_in." % device_str
        ),
        "device": device_str,
    }


def check_osc(ctx, base):
    node = ctx.op(base + "/oscin1")
    if node is None:
        return {"check": "osc", "status": FAIL, "detail": "oscin1 missing"}
    port = _par_value(node, "port")
    active = _par_value(node, "active")
    problems = []
    try:
        if int(port) != 7000:
            problems.append("port=%s (expected 7000)" % port)
    except (TypeError, ValueError):
        problems.append("port unreadable (%r)" % port)
    if not active:
        problems.append("active is off")
    if problems:
        return {"check": "osc", "status": FAIL, "detail": "; ".join(problems)}
    return {"check": "osc", "status": PASS, "detail": "oscin1 active on port 7000"}


def check_syphon(ctx, base):
    node = ctx.op(base + "/syphonOut1")
    if node is None:
        return {"check": "syphon", "status": FAIL, "detail": "syphonOut1 missing"}
    active = _par_value(node, "active")
    sender = _par_value(node, "sendername")
    if sender is None:
        # Par name unknown on this build — report INFO with candidate names
        # rather than guessing (PLAN-01: do not guess the par name).
        name_pars = []
        try:
            name_pars = [p.name for p in node.pars() if "name" in p.name.lower()]
        except Exception:
            pass
        return {
            "check": "syphon",
            "status": INFO,
            "detail": (
                "active=%s; 'sendername' par not found. Candidate name-pars: %s"
                % (bool(active), name_pars)
            ),
        }
    problems = []
    if not active:
        problems.append("active is off")
    if str(sender) != "TDSyphonSpoutOut":
        problems.append("sendername=%r (expected 'TDSyphonSpoutOut')" % str(sender))
    if problems:
        return {"check": "syphon", "status": FAIL, "detail": "; ".join(problems)}
    return {
        "check": "syphon",
        "status": PASS,
        "detail": "syphonOut1 active, sender 'TDSyphonSpoutOut'",
    }


def check_mask_alive(ctx, base):
    node = ctx.op(base + "/body_mask_top")
    if node is None:
        return {
            "check": "mask_alive",
            "status": FAIL,
            "detail": "body_mask_top missing",
        }
    try:
        import numpy as np  # TD ships numpy

        arr = node.numpyArray(delayed=False)
        if arr is None:
            raise ValueError("numpyArray returned None")
        peak = float(np.max(arr))
    except Exception as e:
        return {
            "check": "mask_alive",
            "status": WARN,
            "detail": "could not read body_mask_top pixels: %s" % e,
        }
    if peak > 0.0:
        return {
            "check": "mask_alive",
            "status": PASS,
            "detail": "body_mask_top non-black (peak=%.4f)" % peak,
            "peak": peak,
        }
    return {
        "check": "mask_alive",
        "status": WARN,
        "detail": (
            "body_mask_top is BLACK (peak=0). If movement_tracker.py is NOT "
            "running this is expected — start `python python/movement_tracker.py "
            "--max-people 1` and re-run. If it IS running, the Script TOP isn't "
            "outputting despite a healthy mmap (the June-8 killer)."
        ),
        "peak": peak,
    }


def check_fps(ctx, base):
    rate = getattr(ctx.project, "cookRate", None) if ctx.project is not None else None
    if rate is None:
        return {
            "check": "fps",
            "status": INFO,
            "detail": "project.cookRate unavailable",
        }
    return {
        "check": "fps",
        "status": INFO,
        "detail": (
            "project.cookRate = %s fps. Editor cook rate is not the delivered "
            "rate — confirm 30-60 fps in Perform Mode (F1)." % rate
        ),
        "cook_rate": rate,
    }


# Ordered registry. Entries returning a list (glsl_bindings) are flattened.
_CHECKS = [
    check_ops_exist,
    check_wiring,
    check_glsl_bindings,
    check_uniforms_alive,
    check_audio_device,
    check_osc,
    check_syphon,
    check_mask_alive,
    check_fps,
]


def run_checks(ctx, base="/project1"):
    """Run every check, isolating failures. Returns the full report dict."""
    checks = []
    for fn in _CHECKS:
        try:
            out = fn(ctx, base)
        except Exception as e:  # one broken check must never abort the probe
            checks.append(
                {
                    "check": getattr(fn, "__name__", "unknown"),
                    "status": ERROR,
                    "detail": "probe check raised: %s" % e,
                }
            )
            continue
        if isinstance(out, list):
            checks.extend(out)
        else:
            checks.append(out)

    failed = [c["check"] for c in checks if c.get("status") == FAIL]
    errored = [c["check"] for c in checks if c.get("status") == ERROR]
    if failed or errored:
        result = "FAIL"
    else:
        result = "PASS"

    return {
        "context": ctx.context,
        "timestamp": _timestamp(),
        "base": base,
        "checks": checks,
        "result": result,
        "failed": failed,
        "errored": errored,
    }


def _timestamp():
    """Wall-clock stamp for filenames/report. datetime is stdlib (present in TD)."""
    try:
        from datetime import datetime

        return datetime.now().strftime("%Y%m%d_%H%M%S")
    except Exception:
        return "unknown"


def _counts(checks):
    tally = {}
    for c in checks:
        tally[c.get("status", "?")] = tally.get(c.get("status", "?"), 0) + 1
    return tally


def format_table(report):
    """Aligned PASS/FAIL/WARN table + a RESULT summary line, as a string."""
    checks = report["checks"]
    width = max((len(c.get("check", "")) for c in checks), default=10)
    lines = [
        "",
        "[verify_v2] network probe — context=%s  ts=%s"
        % (report["context"], report["timestamp"]),
        "-" * (width + 60),
    ]
    for c in checks:
        lines.append(
            "  %-6s  %-*s  %s"
            % (c.get("status", "?"), width, c.get("check", ""), c.get("detail", ""))
        )
    lines.append("-" * (width + 60))
    tally = _counts(checks)
    if report["result"] == "PASS":
        total = len(checks)
        green = tally.get(PASS, 0)
        lines.append(
            "[verify_v2] RESULT: PASS (%d/%d green; %d warn, %d info)"
            % (green, total, tally.get(WARN, 0), tally.get(INFO, 0))
        )
    else:
        bad = report["failed"] + report["errored"]
        lines.append(
            "[verify_v2] RESULT: FAIL (%d failed: %s)" % (len(bad), ", ".join(bad))
        )
    return "\n".join(lines)


def write_report(report, logs_dir=LOGS_DIR):
    """Write the report JSON to logs/verify_report_<ts>.json. Returns the path.

    The JSON file — not the Textport — is the channel a future agent reads.
    """
    os.makedirs(logs_dir, exist_ok=True)
    path = os.path.join(logs_dir, "verify_report_%s.json" % report["timestamp"])
    with open(path, "w", newline="\n") as f:
        json.dump(report, f, indent=2)
        f.write("\n")
    return path


def verify(ctx=None, base="/project1", context=None):
    """Top-level entry point: run checks, print the table, write the JSON.

    Returns (report_dict, json_path). Inside TD, call with no arguments — a
    real TDContext is built from the TD globals resolved at the call site.
    """
    if ctx is None:
        ctx = _td_context(context=context or "initial")
    elif context is not None:
        ctx.context = context
    report = run_checks(ctx, base=base)
    print(format_table(report))
    try:
        path = write_report(report)
        print("[verify_v2] JSON report: %s" % path)
    except Exception as e:
        path = None
        print("[verify_v2] WARN: could not write JSON report: %s" % e)
    return report, path


# ----------------------------------------------------------------------------
# TD-global resolution + auto-run. This is the ONLY place bare TD globals are
# referenced, and it is guarded so a plain `import` (pytest) never fires it.
# ----------------------------------------------------------------------------
def _resolve(name):
    """Return a TD global by name, or None outside TD.

    TouchDesigner injects op/project/absTime/run into BUILTINS, not into this
    module's globals(), so a plain globals().get() misses them (the 2026-07-06
    "probe never ran" bug: _IN_TD came back False at the desk even though bare
    op() worked). Check the exec namespace first (for VERIFY_CONTEXT, set by the
    user on the paste line), then builtins.
    """
    if name in globals():
        return globals()[name]
    import builtins

    return getattr(builtins, name, None)


def _td_context(context="initial"):
    """Build a TDContext by resolving TD names as BARE names at call time.

    In TD's ``exec(open(f).read())`` context, op/project/absTime are reachable
    only as bare names (via TD's own name resolution) — NOT via this frame's
    globals() or builtins (both the 2026-07-06 globals() and builtins fixes
    missed them). A bare reference inside this function resolves exactly the way
    the build script's bare op() does. Each is guarded so import stays inert.
    """
    try:
        op_fn = op  # noqa: F821  (TD-provided)
    except NameError:
        op_fn = None
    try:
        project_obj = project  # noqa: F821
    except NameError:
        project_obj = None
    now_fn = None
    try:
        _abs = absTime  # noqa: F821
        now_fn = lambda: _abs.seconds  # noqa: E731
    except NameError:
        pass
    # Persistent cross-paste storage lives on the base COMP's .storage dict.
    storage = {}
    if op_fn is not None:
        try:
            base_comp = op_fn("/project1")
            if (
                base_comp is not None
                and getattr(base_comp, "storage", None) is not None
            ):
                storage = base_comp.storage
        except Exception:
            storage = {}
    return TDContext(
        op=op_fn, project=project_obj, now=now_fn, storage=storage, context=context
    )


# Auto-run only inside TD. `op` resolves as a bare name there (as the build
# script proves); under a plain `import` it raises NameError -> stays inert.
try:
    op  # noqa: F821
    _IN_TD = True
except NameError:
    _IN_TD = False

if _IN_TD:
    _ctx_label = "initial"
    try:
        _ctx_label = VERIFY_CONTEXT or "initial"  # noqa: F821 (set on paste line)
    except NameError:
        pass
    verify(context=_ctx_label)
