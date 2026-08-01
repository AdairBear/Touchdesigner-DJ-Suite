# reset_syphon_alpha.py -- canonical, idempotent reset of the Syphon alpha chain.
#
#   exec(open('/Users/thomasadair/projects/touchdesigner-dj-suite/touchdesigner/scripts/reset_syphon_alpha.py').read())
#
# WHAT THIS FIXES (2026-07-31, from the rig)
# ------------------------------------------
# syphonOut1 was cooking and broadcasting a valid 1280x720 RGBA frame -- OBS was
# receiving it -- but the frame was ~97% TRANSPARENT, so OBS drew its
# transparency checkerboard and no body-graphics ever landed over the camera.
#
# The alpha is computed by the GLSL TOP in front of syphonOut1. Its shader (the
# one this repo shipped in apply_alpha_fix.py, and the code now living in the
# project's alpha Text DAT) is:
#
#       float a = max(c.r, max(c.g, c.b));   // alpha = brightest channel
#       a = a * a;                           // "gamma"
#
# The intent is right -- black background transparent so the OBS camera shows
# through, graphics opaque. The SQUARING is what breaks it. It does not merely
# clean up faint haze; it drags every mid-tone toward zero:
#
#       graphic at 0.5 brightness -> alpha 0.25   (75% transparent)
#       graphic at 0.3 brightness -> alpha 0.09   (91% transparent)
#       graphic at 0.2 brightness -> alpha 0.04   (96% transparent)
#
# Body-outline / aura visuals are exactly this: thin, mid-brightness strokes on
# black. So the graphics were never missing -- they were being published at
# 4-25% opacity over nothing, which reads as "checkerboard, no graphics".
#
# THE FIX: replace the x*x curve with a soft knee that SATURATES. Anything
# meaningfully brighter than the background floor becomes FULLY opaque; only
# true background stays transparent. Same intent, correct transfer function.
#
# This script is safe to run repeatedly. It reuses the nodes that already exist
# rather than creating duplicates, and it verifies its own result by sampling
# the real output alpha -- it prints PASS or FAIL, and on FAIL it tells you
# whether the problem is the alpha (this script's job) or an upstream black
# composite (not this script's job, and it says so rather than pretending).
#
# ---------------------------------------------------------------------------
# EMERGENCY SWITCH -- set True to publish a FULLY OPAQUE frame.
# Use if you are minutes from a show and the overlay is still wrong: the Syphon
# output becomes a solid picture (no camera showing through in OBS), which is
# always visible and never a checkerboard. Equivalent to turning OBS's "Allow
# Transparency" off, but done at the source so it survives an OBS restart.
OPAQUE_MODE = False
# ---------------------------------------------------------------------------

# Alpha transfer tuning. Defaults chosen against the failure above.
ALPHA_THRESHOLD = 0.06  # luminance at/below this stays fully transparent
ALPHA_KNEE = 0.15  # luminance THRESHOLD+KNEE and above is fully opaque
ALPHA_GAIN = 1.0  # post-curve multiplier, clamped to 1.0
ALPHA_FLOOR = 0.0  # minimum alpha anywhere (1.0 == fully opaque frame)

# The rule from the rig: a frame this transparent is a failure, not a look.
FAIL_TRANSPARENT_FRAC = 0.97

import json

P = op("/project1")
report = {}


def say(*a):
    print("[alpha-reset]", *a)


def errs_of(o):
    """errors() is a str in some TD builds and a list in others."""
    try:
        e = o.errors()
    except Exception:
        return ""
    if isinstance(e, (list, tuple)):
        return " ".join(str(x) for x in e).strip()
    return (e or "").strip()


# --- 1. DISCOVER the real chain -------------------------------------------
# By TYPE, not by name. The project has carried several naming generations
# (syphon_alpha/syphon_alpha_glsl from apply_alpha_fix.py;
# syphon_alphaperform/syphon_alpha_gls1 in the live .toe), and guessing wrong
# would silently build a second, disconnected chain next to the real one.

syphons = [
    c
    for c in P.findChildren(depth=1)
    if "syphon" in (c.type or "").lower() or "spout" in (c.type or "").lower()
]
if not syphons:
    say("FAIL: no Syphon Spout Out TOP found under /project1 -- nothing to fix.")
    raise RuntimeError('reset_syphon_alpha: aborted -- see the FAIL line above')
# Prefer the classic name if several exist, else the first one that is active.
SY = op("/project1/syphonOut1") or syphons[0]
say("syphon out:", SY.path, "(type", SY.type + ")")
report["syphon"] = SY.path


def upstream(node, depth=6):
    """Walk back through the inputs, newest first, up to `depth` hops."""
    chain, seen, cur = [], set(), node
    while cur is not None and len(chain) < depth:
        ins = [i for i in cur.inputs if i is not None]
        if not ins:
            break
        cur = ins[0]
        if cur.path in seen:
            break
        seen.add(cur.path)
        chain.append(cur)
    return chain


chain = upstream(SY)
say(
    "upstream chain:",
    " <- ".join(c.name + "(" + c.type + ")" for c in chain) or "(nothing)",
)
report["chain"] = [c.path for c in chain]

# The alpha node: a GLSL TOP anywhere in that chain.
GLSL = next((c for c in chain if "glsl" in (c.type or "").lower()), None)
# The composite source: prefer the known canonical name, else the node feeding
# the GLSL, else whatever feeds the Syphon out.
SRC = (
    op("/project1/final_composite")
    or (([i for i in GLSL.inputs if i is not None] or [None])[0] if GLSL else None)
    or (chain[0] if chain else None)
)
if SRC is None:
    say("FAIL: could not identify a composite source feeding", SY.path)
    raise RuntimeError('reset_syphon_alpha: aborted -- see the FAIL line above')
say("composite source:", SRC.path, "(type", SRC.type + ")")
report["source"] = SRC.path


# --- 2. REPAIR the alpha node ---------------------------------------------
_SHADER = """// Canonical Syphon alpha -- reset_syphon_alpha.py, 2026-07-31.
//
// Replaces the previous "a = max(rgb); a = a*a" curve. The squaring left
// mid-brightness graphics at 4-25% opacity, which published as an almost fully
// transparent frame and drew OBS's checkerboard. A smoothstep knee keeps the
// same intent -- black background transparent, graphics opaque -- but actually
// SATURATES, so anything above the background floor is fully solid.
uniform float uThreshold;   // at/below this luminance -> transparent
uniform float uKnee;        // width of the ramp to fully opaque
uniform float uGain;        // post-curve multiplier
uniform float uFloor;       // minimum alpha (1.0 == force fully opaque)

out vec4 fragColor;

void main()
{
    vec4 c = texture(sTD2DInputs[0], vUV.st);

    // Brightest channel, not luminance: keeps saturated blue/purple/cyan
    // graphics opaque, which a luma weighting would fade out.
    float lum = max(c.r, max(c.g, c.b));

    float a = smoothstep(uThreshold, uThreshold + max(uKnee, 0.001), lum);
    a = clamp(a * uGain, 0.0, 1.0);
    a = max(a, uFloor);

    fragColor = TDOutputSwizzle(vec4(c.rgb, a));
}
"""

if GLSL is None:
    # No alpha node in the chain at all -- build the canonical pair.
    say("no GLSL alpha node in the chain; creating syphon_alpha + syphon_alpha_glsl")
    GLSL = op("/project1/syphon_alpha") or P.create(glslTOP, "syphon_alpha")
    GLSL.nodeX, GLSL.nodeY = SRC.nodeX + 200, SRC.nodeY

# The Text DAT holding the shader: reuse whatever this GLSL is already pointed
# at, so the live node keeps its identity (syphon_alpha_gls1 stays
# syphon_alpha_gls1) instead of gaining a second, ignored copy.
dat_name = ""
try:
    dat_name = (GLSL.par.pixeldat.eval() or "").strip()
except Exception:
    pass
DAT = op(dat_name) if dat_name else None
if DAT is None:
    DAT = (
        op("/project1/syphon_alpha_gls1")
        or op("/project1/syphon_alpha_glsl")
        or P.create(textDAT, "syphon_alpha_glsl")
    )
    DAT.nodeX, DAT.nodeY = GLSL.nodeX, GLSL.nodeY - 120

say("alpha GLSL node:", GLSL.path, "| shader DAT:", DAT.path)
report["glsl"] = GLSL.path
report["dat"] = DAT.path

DAT.text = _SHADER
try:
    GLSL.par.pixeldat = DAT.name
except Exception as e:
    say("could not set pixeldat:", e)

# Uniforms -- same slot idiom the project already uses (_bind_uniforms_v4.py):
# par.uniname<N> + par.value<N>x.
_floor = 1.0 if OPAQUE_MODE else ALPHA_FLOOR
for slot, uname, uval in (
    (1, "uThreshold", ALPHA_THRESHOLD),
    (2, "uKnee", ALPHA_KNEE),
    (3, "uGain", ALPHA_GAIN),
    (4, "uFloor", _floor),
):
    np_ = getattr(GLSL.par, "uniname" + str(slot), None)
    vp_ = getattr(GLSL.par, "value" + str(slot) + "x", None)
    if np_ is None or vp_ is None:
        say("MISSING uniform slot", slot, "-- shader will use its declared default")
        continue
    np_.val = uname
    try:
        vp_.mode = ParMode.CONSTANT
        vp_.expr = ""
    except Exception:
        pass
    vp_.val = float(uval)

# Clear stale slots so an old binding can't shadow ours.
for slot in range(5, 10):
    np_ = getattr(GLSL.par, "uniname" + str(slot), None)
    if np_ is not None and (np_.val or "").startswith("u"):
        np_.val = ""

# Make sure the node is actually doing work.
for pname, want in (("bypass", False), ("active", True)):
    par = getattr(GLSL.par, pname, None)
    if par is not None:
        try:
            par.val = want
        except Exception:
            pass


# --- 3. REWIRE  SRC -> GLSL -> SY ------------------------------------------
# Only these two links are touched. The perform-window / HISENSE branch hangs
# off the composite separately and is deliberately left alone.
if [i for i in GLSL.inputs if i is not None][:1] != [SRC]:
    GLSL.setInputs([SRC])
if [i for i in SY.inputs if i is not None][:1] != [GLSL]:
    SY.setInputs([GLSL])

for node in (SRC, GLSL, SY):
    try:
        node.cook(force=True)
    except Exception as e:
        say("cook failed on", node.path, e)

shader_errs = errs_of(GLSL)
if shader_errs:
    say("SHADER ERRORS:", shader_errs[:400])
    report["shader_errors"] = shader_errs[:400]


# --- 4. VERIFY against the real output -------------------------------------
verdict = "FAIL"
try:
    arr = GLSL.numpyArray()  # HxWx4 float, 0..1
    alpha = arr[..., 3]
    rgb = arr[..., :3]
    src_arr = SRC.numpyArray()
    src_lum = src_arr[..., :3].max(axis=2)

    transparent_frac = float((alpha < 0.02).mean())
    opaque_frac = float((alpha > 0.90).mean())
    graphics_frac = float((alpha > 0.10).mean())

    report.update(
        {
            "alpha_min": round(float(alpha.min()), 4),
            "alpha_max": round(float(alpha.max()), 4),
            "alpha_mean": round(float(alpha.mean()), 4),
            "transparent_frac": round(transparent_frac, 4),
            "opaque_frac": round(opaque_frac, 4),
            "graphics_frac": round(graphics_frac, 4),
            "source_lum_mean": round(float(src_lum.mean()), 4),
            "source_lum_max": round(float(src_lum.max()), 4),
            "rgb_mean": round(float(rgb.mean()), 4),
            "opaque_mode": OPAQUE_MODE,
        }
    )

    say("---------------- RESULT ----------------")
    say(
        "source luminance  mean %.3f  max %.3f"
        % (report["source_lum_mean"], report["source_lum_max"])
    )
    say(
        "output alpha      min %.3f  mean %.3f  max %.3f"
        % (report["alpha_min"], report["alpha_mean"], report["alpha_max"])
    )
    say(
        "transparent %.1f%%   graphics %.1f%%   fully-opaque %.1f%%"
        % (transparent_frac * 100, graphics_frac * 100, opaque_frac * 100)
    )

    if transparent_frac >= FAIL_TRANSPARENT_FRAC:
        if report["source_lum_max"] < 0.10:
            say(
                "FAIL: the frame is %.1f%% transparent BECAUSE THE COMPOSITE FEEDING IT IS BLACK"
                % (transparent_frac * 100)
            )
            say(
                "      (source max luminance %.3f). The alpha chain is now correct;"
                % report["source_lum_max"]
            )
            say(
                "      the break is UPSTREAM of",
                SRC.path,
                "-- check the graphics chain",
            )
            say("      feeding it, or set OPAQUE_MODE = True at the top of this script")
            say("      to publish the picture as-is while you find it.")
            report["diagnosis"] = "upstream_black"
        else:
            say(
                "FAIL: still %.1f%% transparent while the source HAS content"
                % (transparent_frac * 100)
            )
            say(
                "      (source max luminance %.3f). Lower ALPHA_THRESHOLD toward 0.02"
                % report["source_lum_max"]
            )
            say("      and re-run, or set OPAQUE_MODE = True.")
            report["diagnosis"] = "alpha_still_transparent"
    elif report["alpha_max"] < 0.5:
        say(
            "FAIL: nothing in the frame reaches half opacity (max %.3f)."
            % report["alpha_max"]
        )
        report["diagnosis"] = "never_opaque"
    elif graphics_frac < 0.002 and not OPAQUE_MODE:
        say(
            "WARN: only %.2f%% of the frame carries graphics. That can be correct for a"
            % (graphics_frac * 100)
        )
        say("      thin outline, but confirm you can SEE it in OBS before trusting it.")
        verdict = "PASS (sparse -- eyeball it)"
        report["diagnosis"] = "sparse_but_opaque"
    else:
        verdict = "PASS"
        report["diagnosis"] = "ok"

    if verdict.startswith("PASS"):
        say(
            "PASS: Syphon frame is opaque where the graphics are"
            + (
                " (OPAQUE_MODE: whole frame solid)"
                if OPAQUE_MODE
                else " and transparent only on background."
            )
        )
except Exception as e:
    say("FAIL: could not sample the output --", e)
    report["diagnosis"] = "sample_failed"

report["verdict"] = verdict
say("VERDICT:", verdict)

try:
    json.dump(
        report, open("/tmp/td_syphon_alpha_reset.json", "w"), indent=2, default=str
    )
    say("report written to /tmp/td_syphon_alpha_reset.json")
except Exception as e:
    say("could not write report:", e)

say("----------------------------------------")
say("IF PASS -- save the canonical project so this survives a restart:")
say("  1. Look at OBS. The Syphon Client source must now show real graphics,")
say("     not the checkerboard. Confirm with your eyes before saving.")
say("  2. In TD:  File > Save   (Cmd+S) -- this overwrites DJ_Graphics_LIVE.toe")
say("     in place, which is the canonical file the launcher opens.")
say("  3. Do NOT use Save As / an auto-incremented name -- a DJ_Graphics.N.toe")
say("     sibling is the file-explosion failure the agent flags as state_drift.")
say("  4. Re-run this script after re-opening the .toe to confirm it still PASSes.")
