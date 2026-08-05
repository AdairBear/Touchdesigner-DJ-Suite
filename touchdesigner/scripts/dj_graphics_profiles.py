# dj_graphics_profiles.py -- swappable graphics PROFILES for the DJ_Graphics chain
# =============================================================================
# WHAT THIS IS
#   Five pre-show-selectable looks for the live outline/aura chain. A profile is
#   DATA, not a new node graph: it rewrites the palette table and re-binds the
#   parameter EXPRESSIONS that already drive the existing effect nodes. Nothing
#   is created, nothing is deleted, no node is renamed.
#
#   Paste this whole file into the TD Textport (Alt+T) and it lists the
#   profiles. Then apply one:
#
#       apply_profile('STROBE_ACID')
#       list_profiles()                 # names + one-line descriptions
#       show_profile('DEEP_LASER')      # every value the profile will set
#       revert_profile()                # back to UV_RAVE (the shipped look)
#
# -----------------------------------------------------------------------------
# WHY PROFILES AND NOT MORE GENERATIVE LAYERS
#   The look is already fully parameterised. `extend_dj_graphics.py` builds the
#   fx_* chain (palette / trails / kick / snare / evolution) and
#   `td_startup_hooks._apply_rave_look()` then tunes it purely by rewriting a
#   Table DAT and ~9 parameter expressions. So a whole new look costs a table
#   rewrite and a handful of `.expr` assignments -- instant, reversible, and it
#   cannot fail to compile.
#
#   Adding new generative layers instead would mean new GLSL TOPs, which is the
#   single most expensive failure mode this project has (yellow-triangle compile
#   errors, resolution mismatches, GPU load). The rig already runs cookRate 30 to
#   shed load. Variation ACROSS a show is therefore delivered inside each profile
#   -- via the existing LFO/energy evolution layer and a per-profile mode
#   schedule -- rather than by piling on simultaneous nodes.
#
# -----------------------------------------------------------------------------
# THE TWO SAFETY INVARIANTS -- read before changing any number
#
#   1. THE FREEZE. Graphics froze the instant real music played. Root cause
#      (audio_reactive_mapper.py:419) was a CHOP Execute DAT: onValueChange
#      fires once per changed SAMPLE, and audio_spectrum has hundreds of bins,
#      so the handler ran hundreds of times per frame on the cook thread. A
#      second contributor was outline_glow's blur size exploding under a raw
#      audio value.
#
#      THIS FILE ADDS NO AUDIO TAP AND NO CHOP EXECUTE DAT. Every value it
#      reads comes from envelope CHOPs that already exist (`fx_kick_env`,
#      `fx_snare_env`, `fx_master`), through parameter expressions, which TD
#      evaluates once per cook. That is freeze-safe by construction, and
#      `tests/test_dj_graphics_profiles.py` asserts the source stays that way.
#
#      The blur clamp is enforced structurally: `glow_size_expr()` can only ever
#      emit a `min(..., cap)` form, and GLOW_SIZE_HARD_CAP bounds the cap. There
#      is no code path that produces an unclamped glow size.
#
#   2. TRAIL RUNAWAY. fx_trail_hsv.valuemult is the per-frame multiply on a
#      Feedback TOP. At >= 1.0 the feedback accumulates without bound and the
#      frame whites out. Every expression this file emits is clamped by
#      TRAIL_VALUEMULT_HARD_CAP (0.97), so no profile -- and no energy term
#      swing -- can drive it to runaway.
#
#   Neither invariant is left to the caller: both are applied inside the
#   expression builders, so a bad profile value is clamped, not shipped.
#
# -----------------------------------------------------------------------------
# SCOPE -- what this file deliberately does NOT touch
#   * OBS. Nothing here talks to OBS. The "Radio DJ" scene is untouched; Syphon
#     stays overlay-only.
#   * The go-live path. td_startup_hooks.py is NOT modified. Note the
#     consequence: _apply_rave_look() runs on every project load and rewrites
#     the same palette/expressions, so a reload returns you to UV_RAVE. To make
#     a profile survive reloads see PERSISTENCE at the bottom of this file.
#   * Node creation. If the fx_* chain is missing, run extend_dj_graphics.py
#     first; this file reports what is absent and changes nothing.
# =============================================================================

from __future__ import annotations

import colorsys
import json
import os
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

# --- Live network contract ---------------------------------------------------
#: Nodes this file re-binds. Names are fixed by extend_dj_graphics.py and
#: td_startup_hooks._apply_rave_look(); renaming any of them breaks the show.
PARENT = "/project1"

#: Where a chosen profile name is remembered between sessions. Written by
#: apply_profile(); read only by the opt-in startup snippet (see PERSISTENCE).
SELECTION_FILE = os.path.expanduser("~/.dj_graphics_profile.json")

# --- Hard safety bounds (see SAFETY INVARIANTS above) -------------------------
#: Max value the outline_glow blur size expression may reach. The live rig
#: proved ~52px safe (12 base + 40 clamp); anything unbounded refroze the cook.
GLOW_SIZE_HARD_CAP = 52.0
#: Base (silent) glow size. Kept small so the clamp headroom goes to the punch.
GLOW_SIZE_BASE = 12.0
#: Feedback multiply must stay strictly below 1.0 or trails accumulate forever.
TRAIL_VALUEMULT_HARD_CAP = 0.97

# --- Neon/UV palette guard ---------------------------------------------------
#: Hue band (degrees) that muddied to brown in the old CYAN->ORANGE->PURPLE
#: palette once it was multiplied down. Banned outright: this is the "no brown"
#: rule expressed as something a test can actually check.
BROWN_HUE_LO, BROWN_HUE_HI = 15.0, 50.0
#: Neon means bright AND saturated. Both floors are required.
NEON_MIN_VALUE = 0.85
NEON_MIN_SATURATION = 0.70

RGB = Tuple[float, float, float]


# =============================================================================
# PURE CORE -- no TouchDesigner globals below this line until APPLY LAYER.
# Everything here is importable and unit-testable outside TD.
# =============================================================================


class Profile:
    """One selectable look: palette anchors plus a reactivity matrix.

    Every field is a plain number or tuple. Applying a profile writes the
    palette table and re-binds parameter expressions built from these values --
    it never creates, deletes, or renames a node.

    Attributes:
        name: Registry key, uppercase snake case.
        description: One line shown by ``list_profiles()``.
        palette: Colour anchors, each an ``(r, g, b)`` float triple in 0..1.
            The engine sweeps anchor N -> N+1 and wraps. Must pass
            ``validate_profile`` (neon/UV, no brown).
        fire_tint: RGB tint applied to the fire aura layer.
        palette_period_s: Seconds to sweep one anchor to the next.
        kick_advances_palette: If True a kick jumps to the next anchor, so the
            colour moves with the music instead of only with the clock.
        snare_pop: Extra brightness multiplier at full snare (0 = none,
            2.5 = the shipped UV_RAVE pop).
        mono_saturation: Saturation multiply BEFORE the palette multiply. Lower
            = purer neon, because the palette colour dominates.
        outline_base_bright: outline_level brightness floor, in silence.
        outline_kick_gain: Extra outline brightness at full kick.
        glow_kick_gain: Glow blur growth at full kick (clamped, see invariants).
        glow_snare_gain: Glow blur growth at full snare (clamped).
        zoom_kick_gain: Radial scale punch at full kick, as a fraction.
        kick_flash_gain: Brightness of the additive kick flash layer.
        shake_snare_px: Peak snare shake displacement in pixels.
        trail_persistence: Feedback multiply base. Higher = longer trails.
            Clamped below 1.0 on emit.
        trail_energy_gain: How much the 30 s energy accumulator lengthens
            trails in a busy section. 0 disables the energy term.
        mode: ``"cycle"`` alternates the fire/lightning switch, ``"fire"`` or
            ``"lightning"`` locks it to one.
        mode_dwell_s: Seconds per mode when ``mode == "cycle"``.
    """

    def __init__(
        self,
        name: str,
        description: str,
        palette: Sequence[RGB],
        fire_tint: RGB,
        palette_period_s: float = 22.0,
        kick_advances_palette: bool = True,
        snare_pop: float = 2.5,
        mono_saturation: float = 0.12,
        outline_base_bright: float = 2.5,
        outline_kick_gain: float = 6.0,
        glow_kick_gain: float = 40.0,
        glow_snare_gain: float = 15.0,
        zoom_kick_gain: float = 0.25,
        kick_flash_gain: float = 8.0,
        shake_snare_px: float = 8.0,
        trail_persistence: float = 0.89,
        trail_energy_gain: float = 0.0,
        mode: str = "cycle",
        mode_dwell_s: float = 30.0,
    ) -> None:
        self.name = name
        self.description = description
        self.palette = [tuple(float(c) for c in rgb) for rgb in palette]
        self.fire_tint = tuple(float(c) for c in fire_tint)
        self.palette_period_s = float(palette_period_s)
        self.kick_advances_palette = bool(kick_advances_palette)
        self.snare_pop = float(snare_pop)
        self.mono_saturation = float(mono_saturation)
        self.outline_base_bright = float(outline_base_bright)
        self.outline_kick_gain = float(outline_kick_gain)
        self.glow_kick_gain = float(glow_kick_gain)
        self.glow_snare_gain = float(glow_snare_gain)
        self.zoom_kick_gain = float(zoom_kick_gain)
        self.kick_flash_gain = float(kick_flash_gain)
        self.shake_snare_px = float(shake_snare_px)
        self.trail_persistence = float(trail_persistence)
        self.trail_energy_gain = float(trail_energy_gain)
        self.mode = str(mode)
        self.mode_dwell_s = float(mode_dwell_s)

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return "<Profile %s: %s>" % (self.name, self.description)


def rgb_to_hsv_deg(rgb: RGB) -> Tuple[float, float, float]:
    """Convert an RGB triple to ``(hue_degrees, saturation, value)``.

    Args:
        rgb: ``(r, g, b)`` floats in 0..1.

    Returns:
        Hue in 0..360 degrees, saturation and value in 0..1.
    """
    h, s, v = colorsys.rgb_to_hsv(*rgb)
    return h * 360.0, s, v


def is_brown(rgb: RGB) -> bool:
    """Report whether a colour sits in the banned warm band that muddies to brown.

    The old CYAN->ORANGE->PURPLE palette browned because its orange anchor was
    multiplied down against the silhouette. Rather than try to detect "muddy"
    after the fact, the whole orange hue band is banned at source.

    Args:
        rgb: ``(r, g, b)`` floats in 0..1.

    Returns:
        True if the colour would be rejected as brown-forming.
    """
    hue, sat, _val = rgb_to_hsv_deg(rgb)
    if sat < 0.05:  # greys/whites carry no hue, so the band cannot apply
        return False
    return BROWN_HUE_LO <= hue <= BROWN_HUE_HI


def is_neon(rgb: RGB) -> bool:
    """Report whether a colour is bright and saturated enough to read as neon/UV.

    Near-neutral colours (white, near-black) are allowed through as accents;
    the check only constrains colours that actually carry a hue.

    Args:
        rgb: ``(r, g, b)`` floats in 0..1.

    Returns:
        True if the colour satisfies the neon floors.
    """
    _hue, sat, val = rgb_to_hsv_deg(rgb)
    if sat < 0.05:
        return val >= NEON_MIN_VALUE or val <= 0.10  # white-hot or near-black
    return val >= NEON_MIN_VALUE and sat >= NEON_MIN_SATURATION


def validate_profile(profile: Profile) -> List[str]:
    """Check a profile against the palette and safety rules.

    This is the gate that keeps the neon/UV constraint enforceable instead of
    aspirational, and catches out-of-range reactivity values before they reach
    the live network.

    Args:
        profile: The profile to check.

    Returns:
        A list of human-readable problems. Empty means the profile is valid.
    """
    problems: List[str] = []

    if len(profile.palette) < 2:
        problems.append("palette needs at least 2 anchors to sweep between")

    for idx, rgb in enumerate(list(profile.palette) + [profile.fire_tint]):
        label = "fire_tint" if idx == len(profile.palette) else "palette[%d]" % idx
        if len(rgb) != 3:
            problems.append("%s is not an (r, g, b) triple" % label)
            continue
        if any(c < 0.0 or c > 1.0 for c in rgb):
            problems.append("%s %s has a channel outside 0..1" % (label, rgb))
            continue
        if is_brown(rgb):
            hue = rgb_to_hsv_deg(rgb)[0]
            problems.append(
                "%s %s is in the banned brown/orange band (hue %.0f deg, "
                "allowed outside %.0f-%.0f)" % (label, rgb, hue, BROWN_HUE_LO, BROWN_HUE_HI)
            )
        elif not is_neon(rgb):
            _h, sat, val = rgb_to_hsv_deg(rgb)
            problems.append(
                "%s %s is not neon (value %.2f < %.2f or saturation %.2f < %.2f)"
                % (label, rgb, val, NEON_MIN_VALUE, sat, NEON_MIN_SATURATION)
            )

    if profile.trail_persistence >= TRAIL_VALUEMULT_HARD_CAP:
        problems.append(
            "trail_persistence %.3f >= hard cap %.2f -- feedback would run away"
            % (profile.trail_persistence, TRAIL_VALUEMULT_HARD_CAP)
        )
    if profile.trail_persistence < 0.0:
        problems.append("trail_persistence must be >= 0")
    if profile.mode not in ("cycle", "fire", "lightning"):
        problems.append("mode %r must be one of cycle/fire/lightning" % profile.mode)
    if profile.mode == "cycle" and profile.mode_dwell_s <= 0.0:
        problems.append("mode_dwell_s must be > 0 when mode is 'cycle'")
    if profile.palette_period_s <= 0.0:
        problems.append("palette_period_s must be > 0")
    for field in ("glow_kick_gain", "glow_snare_gain", "outline_kick_gain",
                  "zoom_kick_gain", "kick_flash_gain", "shake_snare_px",
                  "snare_pop", "trail_energy_gain"):
        if getattr(profile, field) < 0.0:
            problems.append("%s must be >= 0" % field)

    return problems


# -----------------------------------------------------------------------------
# Expression builders -- pure string functions, each one safety-clamped.
# These are the whole reactivity matrix. Unit-tested without TD.
# -----------------------------------------------------------------------------

KICK = "op('fx_kick_env')['bass']"
SNARE = "op('fx_snare_env')['high']"
ENERGY = "op('fx_master')['bass']"


def glow_size_expr(profile: Profile) -> str:
    """Build the outline_glow blur-size expression, always clamped.

    SAFETY: this function has no branch that emits an unclamped size. The kick
    and snare terms are summed inside a ``min(..., cap)`` whose cap is derived
    from GLOW_SIZE_HARD_CAP, so the blur can never explode under a loud input.
    That clamp is the live-proven half of the freeze fix -- see invariant 1.

    Args:
        profile: Source of the kick/snare gains.

    Returns:
        A TD parameter expression string.
    """
    headroom = max(0.0, GLOW_SIZE_HARD_CAP - GLOW_SIZE_BASE)
    # Clamp the requested gains into the headroom so the expression's own min()
    # is never the only thing standing between us and a runaway blur.
    kick_gain = min(profile.glow_kick_gain, headroom)
    snare_gain = min(profile.glow_snare_gain, headroom)
    return "%g + min(%s*%g + %s*%g, %g)" % (
        GLOW_SIZE_BASE, KICK, kick_gain, SNARE, snare_gain, headroom,
    )


def outline_bright_expr(profile: Profile) -> str:
    """Build the outline_level brightness expression (kick-driven).

    Args:
        profile: Source of the base brightness and kick gain.

    Returns:
        A TD parameter expression string.
    """
    return "%g + %s * %g" % (profile.outline_base_bright, KICK, profile.outline_kick_gain)


def kick_flash_expr(profile: Profile) -> str:
    """Build the additive kick-flash brightness expression.

    Args:
        profile: Source of the flash gain.

    Returns:
        A TD parameter expression string.
    """
    return "1 + %s * %g" % (KICK, profile.kick_flash_gain)


def zoom_expr(profile: Profile) -> str:
    """Build the radial scale-punch expression for the kick expand stage.

    Args:
        profile: Source of the zoom gain.

    Returns:
        A TD parameter expression string.
    """
    return "1 + %s * %g" % (KICK, profile.zoom_kick_gain)


def shake_expr(profile: Profile, axis: int, out_w: int = 1280) -> str:
    """Build one axis of the snare shake expression.

    Transform TOP translate is a fraction of resolution, so the pixel figure is
    divided by width. The noise channel gives the shake a direction that is not
    correlated between axes.

    Args:
        profile: Source of the shake magnitude.
        axis: 0 for x, 1 for y.
        out_w: Output width in pixels, used to convert px to a fraction.

    Returns:
        A TD parameter expression string.
    """
    frac = profile.shake_snare_px / float(out_w)
    return "%s * op('fx_noise')[%d] * %g" % (SNARE, axis, frac)


def trail_valuemult_expr(profile: Profile, with_energy: bool = True) -> str:
    """Build the feedback decay expression, hard-clamped below runaway.

    SAFETY: a Feedback TOP whose value multiply reaches 1.0 accumulates without
    bound and whites out the frame. The whole expression is wrapped in
    ``min(..., TRAIL_VALUEMULT_HARD_CAP)`` so neither the profile's base nor the
    energy term's upward swing can cross that line -- see invariant 2.

    The energy term uses fx_master, the existing 30 s beat-density accumulator
    mapped to roughly 0.6..1.5, so a busy section leaves longer trails than a
    sparse one. Subtracting 1.0 centres it, making the term signed.

    Args:
        profile: Source of the persistence base and energy gain.
        with_energy: False when fx_master is absent from the network, which
            drops the energy term rather than emitting a broken reference.

    Returns:
        A TD parameter expression string.
    """
    base = min(profile.trail_persistence, TRAIL_VALUEMULT_HARD_CAP)
    terms = "%g - op('fx_lfo_decay')['chan1'] * 0.03" % base
    if with_energy and profile.trail_energy_gain > 0.0:
        terms += " + (%s - 1.0) * %g" % (ENERGY, profile.trail_energy_gain)
    return "min(%s, %g)" % (terms, TRAIL_VALUEMULT_HARD_CAP)


def mode_index_expr(profile: Profile) -> str:
    """Build the visual_switch index expression for this profile's mode schedule.

    visual_switch has exactly two inputs (fire_glsl, light_glsl), so the
    schedule alternates between them or locks to one. No new GLSL is involved.

    Args:
        profile: Source of the mode and dwell time.

    Returns:
        A TD parameter expression string.
    """
    if profile.mode == "fire":
        return "0"
    if profile.mode == "lightning":
        return "1"
    return "int(absTime.seconds / %g) %% 2" % profile.mode_dwell_s


def palette_engine_code(profile: Profile) -> str:
    """Build the Script CHOP source that sweeps and pops the palette.

    Structurally identical to the shipped rave engine, but parameterised: the
    sweep period, the snare pop depth, and whether a kick advances the anchor
    all come from the profile.

    FREEZE SAFETY: this is a Script CHOP ``onCook``, which TD calls once per
    cook. It is emphatically NOT a CHOP Execute ``onValueChange``, which is what
    fired once per FFT bin and froze the cook. Do not convert it.

    Args:
        profile: Source of period, pop depth and kick-advance behaviour.

    Returns:
        Python source for the fx_palette_engine callback DAT.
    """
    return (
        "# fx_palette_engine -- generated by dj_graphics_profiles.py\n"
        "# profile: %s\n"
        "# Script CHOP onCook == once per cook. Never make this a CHOP Execute\n"
        "# onValueChange: that fires once per FFT bin and refreezes the cook.\n"
        "_kick_jump = 0\n"
        "_kick_prev = 0.0\n"
        "KICK_ADVANCES = %s\n"
        "PERIOD = %g\n"
        "POP = %g\n"
        "def onCook(scriptOp):\n"
        "    global _kick_jump, _kick_prev\n"
        "    scriptOp.clear()\n"
        "    tbl = op('fx_palette_table')\n"
        "    names = ('primaryR','primaryG','primaryB',"
        "'secondaryR','secondaryG','secondaryB')\n"
        "    if tbl is None or tbl.numRows == 0:\n"
        "        for nm in names:\n"
        "            scriptOp.appendChan(nm).vals = [1.0]\n"
        "        return\n"
        "    n = tbl.numRows\n"
        "    ke = op('fx_kick_env')\n"
        "    kv = 0.0\n"
        "    if ke is not None and ke.numChans > 0:\n"
        "        try:\n"
        "            kv = ke['bass'].eval()\n"
        "        except Exception:\n"
        "            kv = ke[0].eval()\n"
        "    if KICK_ADVANCES and kv > 0.5 and _kick_prev <= 0.5:\n"
        "        _kick_jump += 1\n"
        "    _kick_prev = kv\n"
        "    se = op('fx_snare_env')\n"
        "    sv = 0.0\n"
        "    if se is not None and se.numChans > 0:\n"
        "        try:\n"
        "            sv = se['high'].eval()\n"
        "        except Exception:\n"
        "            sv = se[0].eval()\n"
        "    bright = 1.0 + sv * POP\n"
        "    pos = (absTime.seconds / PERIOD) + _kick_jump\n"
        "    idx = int(pos) %% n\n"
        "    nxt = (idx + 1) %% n\n"
        "    f = pos - int(pos)\n"
        "    def cell(r, c):\n"
        "        try:\n"
        "            return float(tbl[r, c].val)\n"
        "        except Exception:\n"
        "            return 0.0\n"
        "    for col, nm in enumerate(names):\n"
        "        a = cell(idx, col)\n"
        "        b = cell(nxt, col)\n"
        "        scriptOp.appendChan(nm).vals = [(a + (b - a) * f) * bright]\n"
        "    return\n"
    ) % (profile.name, "True" if profile.kick_advances_palette else "False",
         profile.palette_period_s, profile.snare_pop)


def palette_rows(profile: Profile) -> List[List[str]]:
    """Build the fx_palette_table rows for a profile.

    Each row is ``primary + secondary``, where secondary is the next anchor, so
    the engine can crossfade row N toward row N+1 and wrap at the end.

    Args:
        profile: Source of the colour anchors.

    Returns:
        Rows of six formatted float strings, ready for ``appendRow``.
    """
    anchors = profile.palette
    rows: List[List[str]] = []
    for i, primary in enumerate(anchors):
        secondary = anchors[(i + 1) % len(anchors)]
        rows.append(["%.4f" % v for v in tuple(primary) + tuple(secondary)])
    return rows


# -----------------------------------------------------------------------------
# THE REGISTRY -- five looks, all neon/UV, all validated by the test suite.
# -----------------------------------------------------------------------------

# Shared neon anchors. Every one sits outside the banned 15-50 deg brown band.
CYAN: RGB = (0.0, 1.0, 1.0)
MAGENTA: RGB = (1.0, 0.0, 1.0)
ACID: RGB = (0.35, 1.0, 0.06)
PINK: RGB = (1.0, 0.06, 0.55)
VIOLET: RGB = (0.6, 0.0, 1.0)
BLUE: RGB = (0.1, 0.35, 1.0)
WHITE_HOT: RGB = (1.0, 1.0, 1.0)

PROFILES: Dict[str, Profile] = {}


def register(profile: Profile) -> Profile:
    """Add a profile to the registry.

    Args:
        profile: The profile to register.

    Returns:
        The same profile, so this can wrap a constructor call.
    """
    PROFILES[profile.name] = profile
    return profile


register(Profile(
    name="UV_RAVE",
    description="The shipped look. Full-spectrum neon sweep, kick jumps colour, big snare pop.",
    palette=[CYAN, MAGENTA, ACID, PINK, VIOLET],
    fire_tint=(1.0, 0.1, 0.9),
    palette_period_s=22.0,
    kick_advances_palette=True,
    snare_pop=2.5,
    outline_base_bright=2.5,
    outline_kick_gain=6.0,
    glow_kick_gain=40.0,
    glow_snare_gain=15.0,
    zoom_kick_gain=0.25,
    kick_flash_gain=8.0,
    shake_snare_px=8.0,
    trail_persistence=0.89,
    trail_energy_gain=0.03,
    mode="cycle",
    mode_dwell_s=30.0,
))

register(Profile(
    name="DEEP_LASER",
    description="Deep/rolling. Long cold trails, slow sweep, locked to lightning, energy-fed.",
    palette=[CYAN, BLUE, VIOLET, MAGENTA],
    fire_tint=(0.3, 0.2, 1.0),
    palette_period_s=45.0,
    kick_advances_palette=False,
    snare_pop=1.2,
    mono_saturation=0.08,
    outline_base_bright=2.0,
    outline_kick_gain=4.0,
    glow_kick_gain=28.0,
    glow_snare_gain=8.0,
    zoom_kick_gain=0.12,
    kick_flash_gain=4.0,
    shake_snare_px=3.0,
    trail_persistence=0.94,
    trail_energy_gain=0.02,
    mode="lightning",
))

register(Profile(
    name="STROBE_ACID",
    description="Peak time. Near-zero trails, violent kick flash and zoom, fast mode cycle.",
    palette=[ACID, MAGENTA, WHITE_HOT, CYAN],
    fire_tint=(0.6, 1.0, 0.1),
    palette_period_s=8.0,
    kick_advances_palette=True,
    snare_pop=4.0,
    mono_saturation=0.05,
    outline_base_bright=3.0,
    outline_kick_gain=9.0,
    glow_kick_gain=40.0,
    glow_snare_gain=12.0,
    zoom_kick_gain=0.40,
    kick_flash_gain=12.0,
    shake_snare_px=14.0,
    trail_persistence=0.74,
    trail_energy_gain=0.0,
    mode="cycle",
    mode_dwell_s=8.0,
))

register(Profile(
    name="VAPOR_UV",
    description="Melodic/softer. Pink-violet wash, gentle kick, wide sweep, locked to fire.",
    palette=[PINK, VIOLET, MAGENTA, CYAN],
    fire_tint=(1.0, 0.2, 0.8),
    palette_period_s=30.0,
    kick_advances_palette=False,
    snare_pop=1.8,
    mono_saturation=0.18,
    outline_base_bright=2.2,
    outline_kick_gain=3.5,
    glow_kick_gain=24.0,
    glow_snare_gain=14.0,
    zoom_kick_gain=0.10,
    kick_flash_gain=3.0,
    shake_snare_px=4.0,
    trail_persistence=0.92,
    trail_energy_gain=0.04,
    mode="fire",
))

register(Profile(
    name="MONO_PULSE",
    description="Minimal/clean. Single cyan-to-white axis; all reactivity in brightness and glow.",
    palette=[CYAN, WHITE_HOT, CYAN, BLUE],
    fire_tint=(0.2, 0.9, 1.0),
    palette_period_s=16.0,
    kick_advances_palette=True,
    snare_pop=3.0,
    mono_saturation=0.02,
    outline_base_bright=2.0,
    outline_kick_gain=10.0,
    glow_kick_gain=40.0,
    glow_snare_gain=15.0,
    zoom_kick_gain=0.18,
    kick_flash_gain=10.0,
    shake_snare_px=2.0,
    trail_persistence=0.85,
    trail_energy_gain=0.05,
    mode="cycle",
    mode_dwell_s=45.0,
))

#: Falling back here is always safe: it is the look currently shipped by
#: td_startup_hooks._apply_rave_look().
DEFAULT_PROFILE = "UV_RAVE"


def profile_plan(profile: Profile, with_energy: bool = True) -> Dict[str, Any]:
    """Describe every value a profile would write, without touching TD.

    This is what ``show_profile()`` prints and what the tests assert against, so
    a profile can be fully reviewed before it ever reaches the live rig.

    Args:
        profile: The profile to describe.
        with_energy: Whether fx_master is available for the trail energy term.

    Returns:
        A dict of node -> {parameter: value-or-expression}.
    """
    return {
        "fx_palette_table": {"rows": palette_rows(profile)},
        "fx_palette_engine_cb": {"text": palette_engine_code(profile)},
        "fx_palette_mono": {"saturationmult": profile.mono_saturation},
        "outline_level": {"brightness1": outline_bright_expr(profile)},
        "outline_glow": {"size": glow_size_expr(profile)},
        "fx_kick_bright": {"brightness1": kick_flash_expr(profile)},
        "fx_kick_expand": {"scale": zoom_expr(profile)},
        "fx_snare_shake": {
            "tx": shake_expr(profile, 0),
            "ty": shake_expr(profile, 1),
        },
        "fx_trail_hsv": {"valuemult": trail_valuemult_expr(profile, with_energy)},
        "fire_tint": {
            "colorr": profile.fire_tint[0],
            "colorg": profile.fire_tint[1],
            "colorb": profile.fire_tint[2],
        },
        "visual_switch": {"index": mode_index_expr(profile)},
    }


# =============================================================================
# APPLY LAYER -- everything below needs a live TouchDesigner.
# Guarded so the module stays importable (and testable) outside TD.
# =============================================================================


def _in_td() -> bool:
    """Report whether TD's globals are present, i.e. we are inside TouchDesigner.

    Resolve the name rather than inspecting ``__builtins__``: that attribute is
    the builtins MODULE in ``__main__`` but a plain DICT inside an imported
    module, and ``dir()`` on the dict returns its methods, not its keys. A
    membership test would therefore report "not in TD" while running in TD, and
    apply_profile() would silently do nothing at the rig. Letting Python's own
    name lookup answer the question is correct in both cases.

    Returns:
        True when running inside TouchDesigner, False when imported by pytest.
    """
    try:
        op  # noqa: B018, F821 - TD injects this; NameError means we are outside TD
        return True
    except NameError:
        return False


def _log(msg: str) -> None:
    """Print a namespaced line to the Textport.

    Args:
        msg: The message body.
    """
    print("[dj_profiles] " + msg)


def _resolve(name: str) -> Optional[Any]:
    """Look up a node under PARENT, returning None instead of raising.

    Args:
        name: Node name relative to PARENT.

    Returns:
        The operator, or None if absent.
    """
    try:
        return op(PARENT + "/" + name)  # noqa: F821 - TD global
    except Exception:
        return None


def _set_expr(node: Any, par_names: Sequence[str], expr: str, report: List[str]) -> bool:
    """Bind the first parameter in ``par_names`` that exists on ``node``.

    Parameter names drift between TD builds (scale vs sx vs scalex), so every
    write tries a list of candidates and records the outcome rather than
    assuming one spelling.

    Args:
        node: Target operator.
        par_names: Candidate parameter names, most likely first.
        expr: Expression to bind.
        report: Mutable list collecting human-readable outcomes.

    Returns:
        True if a parameter was bound.
    """
    for par_name in par_names:
        if hasattr(node.par, par_name):
            try:
                getattr(node.par, par_name).expr = expr
                report.append("OK   %s.%s = %s" % (node.name, par_name, expr))
                return True
            except Exception as exc:
                report.append("ERR  %s.%s: %s" % (node.name, par_name, exc))
                return False
    report.append("SKIP %s has none of %s" % (node.name, list(par_names)))
    return False


def _set_val(node: Any, par_names: Sequence[str], value: Any, report: List[str]) -> bool:
    """Set the first parameter in ``par_names`` that exists on ``node``.

    Args:
        node: Target operator.
        par_names: Candidate parameter names, most likely first.
        value: Value to write.
        report: Mutable list collecting human-readable outcomes.

    Returns:
        True if a parameter was written.
    """
    for par_name in par_names:
        if hasattr(node.par, par_name):
            try:
                setattr(getattr(node.par, par_name), "val", value)
                report.append("OK   %s.%s = %r" % (node.name, par_name, value))
                return True
            except Exception as exc:
                report.append("ERR  %s.%s: %s" % (node.name, par_name, exc))
                return False
    report.append("SKIP %s has none of %s" % (node.name, list(par_names)))
    return False


def _step(label: str, fn: Callable[[], None], report: List[str]) -> None:
    """Run one application step in isolation.

    Mirrors td_startup_hooks._apply_rave_look: a wrong parameter name on one
    node must never abort the rest of the profile mid-show.

    Args:
        label: Step name for the log.
        fn: The step body.
        report: Mutable list collecting human-readable outcomes.
    """
    try:
        fn()
    except Exception as exc:
        report.append("ERR  %s: %s" % (label, exc))


def list_profiles() -> List[str]:
    """Print and return the available profile names.

    Returns:
        Profile names in registry order.
    """
    _log("available profiles:")
    for name, prof in PROFILES.items():
        marker = "*" if name == DEFAULT_PROFILE else " "
        _log("  %s %-12s %s" % (marker, name, prof.description))
    _log("apply with:  apply_profile('NAME')     * = shipped default")
    return list(PROFILES)


def show_profile(name: str = DEFAULT_PROFILE) -> Optional[Dict[str, Any]]:
    """Print every value a profile would write, without applying it.

    Args:
        name: Registry key.

    Returns:
        The plan dict, or None if the name is unknown.
    """
    prof = PROFILES.get(name)
    if prof is None:
        _log("unknown profile %r -- try list_profiles()" % name)
        return None
    problems = validate_profile(prof)
    _log("=== %s === %s" % (prof.name, prof.description))
    if problems:
        for p in problems:
            _log("  INVALID: " + p)
    plan = profile_plan(prof)
    for node, pars in plan.items():
        for par, val in pars.items():
            if par == "text":
                _log("  %-20s %-14s <%d chars of engine source>"
                     % (node, par, len(str(val))))
            elif par == "rows":
                _log("  %-20s %-14s %d palette rows" % (node, par, len(val)))
            else:
                _log("  %-20s %-14s %s" % (node, par, val))
    return plan


def apply_profile(name: str = DEFAULT_PROFILE) -> Dict[str, Any]:
    """Apply a profile to the live network.

    Idempotent and re-runnable: it only rewrites a table and re-binds
    expressions, so applying the same profile twice is a no-op in effect.
    Never raises -- every step is isolated, and a missing node is reported
    rather than thrown.

    Args:
        name: Registry key. Unknown names abort without touching anything.

    Returns:
        A result dict with ``profile``, ``applied`` (bool) and ``report``
        (list of per-step outcome lines).
    """
    result: Dict[str, Any] = {"profile": name, "applied": False, "report": []}
    report: List[str] = result["report"]

    prof = PROFILES.get(name)
    if prof is None:
        _log("unknown profile %r -- try list_profiles()" % name)
        report.append("ERR  unknown profile %r" % name)
        return result

    problems = validate_profile(prof)
    if problems:
        # A profile that fails its own palette/safety rules is a bug in this
        # file, not something to push at the rig mid-show.
        for p in problems:
            _log("INVALID: " + p)
        report.append("ERR  profile failed validation; nothing applied")
        return result

    if not _in_td():
        _log("not running inside TouchDesigner -- nothing applied")
        report.append("ERR  no TD context")
        return result

    _log("=== applying %s === %s" % (prof.name, prof.description))

    # fx_master only exists once extend_dj_graphics.py has built the evolution
    # layer. Without it, drop the energy term rather than bind a dead reference.
    has_energy = _resolve("fx_master") is not None
    if not has_energy:
        report.append("WARN fx_master absent -- trail energy term disabled")

    missing: List[str] = []

    def _need(node_name: str) -> Optional[Any]:
        node = _resolve(node_name)
        if node is None:
            missing.append(node_name)
        return node

    # --- palette table -------------------------------------------------------
    def _palette() -> None:
        tbl = _need("fx_palette_table")
        if tbl is None:
            return
        tbl.clear()
        for row in palette_rows(prof):
            tbl.appendRow(row)
        report.append("OK   fx_palette_table = %d rows" % len(prof.palette))
    _step("palette", _palette, report)

    # --- palette engine ------------------------------------------------------
    def _engine() -> None:
        cb = _need("fx_palette_engine_cb")
        if cb is None:
            return
        cb.text = palette_engine_code(prof)
        engine = _resolve("fx_palette_engine")
        if engine is not None:
            engine.cook(force=True)
        report.append("OK   fx_palette_engine_cb = %s engine (period %gs, pop %g)"
                      % (prof.name, prof.palette_period_s, prof.snare_pop))
    _step("engine", _engine, report)

    # --- saturation floor before the palette multiply ------------------------
    def _mono() -> None:
        node = _resolve("fx_palette_mono")
        if node is None:
            report.append("WARN fx_palette_mono absent -- skipping saturation")
            return
        _set_val(node, ["saturationmult", "saturationmultiply", "saturation"],
                 prof.mono_saturation, report)
    _step("mono", _mono, report)

    # --- reactivity matrix ---------------------------------------------------
    def _outline() -> None:
        node = _need("outline_level")
        if node is not None:
            _set_expr(node, ["brightness1", "brightness"], outline_bright_expr(prof), report)
    _step("outline_bright", _outline, report)

    def _glow() -> None:
        node = _need("outline_glow")
        if node is not None:
            # Always the clamped form. See invariant 1.
            _set_expr(node, ["size"], glow_size_expr(prof), report)
    _step("glow", _glow, report)

    def _flash() -> None:
        node = _need("fx_kick_bright")
        if node is not None:
            _set_expr(node, ["brightness1", "brightness"], kick_flash_expr(prof), report)
    _step("kick_flash", _flash, report)

    def _zoom() -> None:
        node = _need("fx_kick_expand")
        if node is None:
            return
        expr = zoom_expr(prof)
        for a, b in (("sx", "sy"), ("scalex", "scaley")):
            if hasattr(node.par, a) and hasattr(node.par, b):
                _set_expr(node, [a], expr, report)
                _set_expr(node, [b], expr, report)
                return
        _set_expr(node, ["scale"], expr, report)
    _step("zoom", _zoom, report)

    def _shake() -> None:
        node = _resolve("fx_snare_shake")
        if node is None:
            report.append("WARN fx_snare_shake absent (GLSL split mode?) -- skipping")
            return
        _set_expr(node, ["tx", "translatex"], shake_expr(prof, 0), report)
        _set_expr(node, ["ty", "translatey"], shake_expr(prof, 1), report)
    _step("shake", _shake, report)

    def _trails() -> None:
        node = _need("fx_trail_hsv")
        if node is not None:
            # Always the clamped form. See invariant 2.
            _set_expr(node, ["valuemult", "valuemultiply"],
                      trail_valuemult_expr(prof, has_energy), report)
    _step("trails", _trails, report)

    def _fire() -> None:
        node = _need("fire_tint")
        if node is None:
            return
        for par, val in zip(("colorr", "colorg", "colorb"), prof.fire_tint):
            _set_val(node, [par], val, report)
    _step("fire_tint", _fire, report)

    def _mode() -> None:
        node = _need("visual_switch")
        if node is not None:
            _set_expr(node, ["index"], mode_index_expr(prof), report)
    _step("mode", _mode, report)

    if missing:
        report.append("WARN missing nodes: %s (run extend_dj_graphics.py first)"
                      % ", ".join(sorted(set(missing))))

    result["applied"] = True
    result["missing"] = sorted(set(missing))
    _remember(name, report)

    for line in report:
        _log("  " + line)
    errors = sum(1 for line in report if line.startswith("ERR"))
    _log("=== %s applied: %d steps, %d errors, %d missing nodes ==="
         % (prof.name, len(report), errors, len(result["missing"])))
    if missing:
        _log("NOTE a project RELOAD re-runs td_startup_hooks._apply_rave_look(),")
        _log("     which resets this look to UV_RAVE. See PERSISTENCE in this file.")
    return result


def revert_profile() -> Dict[str, Any]:
    """Reapply the shipped default look.

    Returns:
        The same result dict ``apply_profile`` returns.
    """
    _log("reverting to the shipped default (%s)" % DEFAULT_PROFILE)
    return apply_profile(DEFAULT_PROFILE)


def _remember(name: str, report: List[str]) -> None:
    """Record the chosen profile so an opt-in startup hook could restore it.

    Writing this file has no effect on its own -- nothing reads it unless the
    PERSISTENCE snippet below is installed. Failure is non-fatal by design: a
    read-only home directory must not break a live show.

    Args:
        name: The profile just applied.
        report: Mutable list collecting human-readable outcomes.
    """
    try:
        with open(SELECTION_FILE, "w") as handle:
            json.dump({"profile": name}, handle)
        report.append("OK   remembered %r in %s" % (name, SELECTION_FILE))
    except Exception as exc:
        report.append("WARN could not write %s: %s" % (SELECTION_FILE, exc))


def selected_profile() -> str:
    """Read back the remembered profile name, falling back to the default.

    Returns:
        A profile name that is guaranteed to exist in the registry.
    """
    try:
        with open(SELECTION_FILE) as handle:
            name = json.load(handle).get("profile", DEFAULT_PROFILE)
        return name if name in PROFILES else DEFAULT_PROFILE
    except Exception:
        return DEFAULT_PROFILE


# =============================================================================
# PERSISTENCE (opt-in -- NOT installed by this file)
#
#   td_startup_hooks._apply_rave_look() runs on every project load and rewrites
#   the same palette table and expressions this file sets. That is deliberate:
#   the startup hook owns the go-live path and always brings the rig up in the
#   known-good UV_RAVE look. The cost is that a reload discards your selection.
#
#   To make the selection survive reloads, add ONE entry to the tuple in
#   td_startup_hooks._run(), AFTER ("rave_look", _apply_rave_look) so it wins:
#
#       ("graphics_profile", _apply_selected_graphics_profile),
#
#   and this function beside it:
#
#       def _apply_selected_graphics_profile():
#           import sys
#           sys.path.insert(0, "/Users/thomasadair/projects/"
#                              "touchdesigner-dj-suite/touchdesigner/scripts")
#           import dj_graphics_profiles as gp
#           gp.apply_profile(gp.selected_profile())
#
#   Left uninstalled on purpose: it changes what happens at showtime, and that
#   is your call, not this file's.
# =============================================================================


def _autorun() -> None:
    """Greet on paste: show the profiles rather than silently changing the rig."""
    _log("=================================================")
    _log("dj_graphics_profiles -- pre-show look selection")
    _log("=================================================")
    list_profiles()
    _log("remembered selection: %s" % selected_profile())
    _log("nothing applied yet -- call apply_profile('NAME') when you're ready.")


if _in_td():  # pragma: no cover - only true inside TouchDesigner
    _autorun()
