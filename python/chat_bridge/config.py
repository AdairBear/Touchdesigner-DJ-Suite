"""Every tunable number the chat bridge obeys, in one place.

Kept as module constants rather than a config file on purpose: these are safety
bounds, not preferences. A number that can be edited from outside the repo is a
number an audience can eventually reach, and §2.2 of the scope is explicit that
the ceiling must not be reachable from chat.

The photosensitivity block at the bottom is the one section that is NOT a
tunable. It has no OSC address, no environment override, and no code path that
raises it. See :mod:`chat_bridge.arbiter` and ``audience_control.py`` for the
two independent enforcement points.
"""

from __future__ import annotations

import os
from typing import Dict, Tuple

# --- Wire ---------------------------------------------------------------------
#: Where TouchDesigner's OSC In DAT listens. Shared with the TouchOSC buttons;
#: audience traffic is separated by ADDRESS namespace, never by port, so the
#: TD-side kill switch can gate one and not the other (scope §4.3).
TD_OSC_HOST = os.environ.get("CHAT_BRIDGE_TD_HOST", "127.0.0.1")
TD_OSC_PORT = int(os.environ.get("CHAT_BRIDGE_TD_PORT", "7400"))

#: The bridge's own control listener. Distinct from 7400 because two processes
#: cannot bind the same UDP port; TouchOSC's kill switch is configured to send
#: to both, so neither gate depends on the other being alive.
BRIDGE_CONTROL_PORT = int(os.environ.get("CHAT_BRIDGE_CONTROL_PORT", "7401"))

#: Audience OSC address prefix. Deliberately NOT ``/dj/profile`` -- that
#: namespace belongs to Thomas alone, and the whole point of the split is that
#: disabling the audience must not disable his own buttons.
AUDIENCE_PREFIX = "/dj/audience"
#: Thomas's own prefix, re-declared here so the emitter can assert it never
#: emits into it.
OPERATOR_PREFIX = "/dj/profile"

# --- Clock --------------------------------------------------------------------
#: Seconds of chat gathered into one LLM call.
BATCH_S = 10.0
#: Seconds of batches tallied into one PROFILE decision. ~1 decision / 30-60 s.
VOTE_WINDOW_S = 30.0
#: Main loop tick. Small enough that a one-shot feels immediate.
TICK_S = 0.25
#: A heartbeat line every N seconds, so absence is detectable (fail-loud rule:
#: "I haven't heard a heartbeat in N minutes" catches whole-path death that
#: per-event error handlers miss).
HEARTBEAT_S = 30.0

# --- Rate limits (scope §3.2) -------------------------------------------------
#: One accepted request per viewer per this many seconds.
PER_USER_COOLDOWN_S = 90.0
#: Accepted requests per viewer per bridge run.
PER_USER_DAILY_CAP = 20
#: Intake ceiling. A raid must not exhaust memory or LLM budget.
INTAKE_MAX_PER_S = 20.0
INTAKE_QUEUE_MAX = 500
#: Global per-verb cooldown -- the thrash guard. Re-checked TD-side.
ACTION_COOLDOWN_S: Dict[str, float] = {
    "PROFILE": 60.0,
    "NUDGE": 10.0,
    "ONESHOT": 6.0,
}
#: A PROFILE change needs this many distinct voters. One viewer must not be
#: able to flip the whole look; a single-viewer stream degrades to nudges and
#: one-shots, which is the right behaviour.
PROFILE_QUORUM = 2
#: Actions the interpreter is less sure of than this are dropped.
MIN_CONFIDENCE = 0.55

# --- The closed vocabularies (scope §2.1) -------------------------------------
#: PROFILE targets are NOT listed here. They are read live from
#: ``dj_graphics_profiles.PROFILES`` at validation time, so this file cannot
#: drift from the registry -- see validator.valid_profile_targets().
VERBS: Tuple[str, ...] = ("PROFILE", "NUDGE", "ONESHOT", "NONE")

NUDGE_TARGETS: Tuple[str, ...] = (
    "GLOW", "FLASH", "TRAILS", "SHAKE", "ZOOM", "SPEED",
)

ONESHOT_TARGETS: Tuple[str, ...] = (
    "STROBE_BURST", "COLOR_POP", "WHITEOUT",
)

#: Colour words resolve to these names only. The audience cannot author an RGB
#: triple, so it cannot route around the neon/brown palette guards.
COLOUR_NAMES: Tuple[str, ...] = (
    "CYAN", "MAGENTA", "ACID", "PINK", "VIOLET", "BLUE", "WHITE_HOT",
)

#: Nudge target -> fx_audience channel. The channel names are owned by
#: dj_graphics_profiles.AUDIENCE_CHANNELS; this map is asserted against it in
#: the tests, so a rename there fails loudly here.
NUDGE_CHANNEL: Dict[str, str] = {
    "GLOW": "gain_glow",
    "FLASH": "gain_flash",
    "TRAILS": "trail_bias",
    "SHAKE": "shake",
    "ZOOM": "zoom",
    "SPEED": "speed",
}

#: Nudge amounts are clamped to this before they leave the bridge, clamped
#: again by the TD handler, and clamped a third time inside the parameter
#: expression itself.
NUDGE_MIN, NUDGE_MAX = -1.0, 1.0

# --- Operator override (scope §4) ---------------------------------------------
#: Any /dj/profile/* from TouchOSC arms this. Audience actions are received,
#: tallied and logged during it -- just not applied. A timer, not a mode, so it
#: self-clears and Thomas never has to remember to re-enable anything.
OPERATOR_LOCKOUT_S = 60.0
#: PANIC means something went wrong, so it holds the room longer.
PANIC_LOCKOUT_S = 300.0

# --- Moderation ---------------------------------------------------------------
MODERATION_MODEL = "omni-moderation-latest"
MODERATION_TIMEOUT_S = 0.3
#: Consecutive moderation failures before an operator alert. A silently
#: degraded moderation layer is exactly the "how would I find out?" landmine.
MODERATION_ALERT_AFTER = 3
#: Longest display name rendered anywhere.
NAME_MAX_LEN = 20
#: Longest message text the pipeline will even look at.
TEXT_MAX_LEN = 200

# --- Interpreter --------------------------------------------------------------
INTERPRETER_MODEL = os.environ.get("CHAT_BRIDGE_MODEL", "gpt-4.1-mini")
INTERPRETER_TIMEOUT_S = 8.0
#: Chat lines per LLM call. Beyond this the batch is truncated (oldest dropped)
#: rather than allowed to grow the prompt without bound.
BATCH_MAX_LINES = 40

# =============================================================================
# PHOTOSENSITIVITY CEILING -- NOT NEGOTIABLE, NOT VOTEABLE, NOT CONFIGURABLE
# =============================================================================
# A live stream with flashing visuals has a duty of care. There is deliberately
# no OSC address, no environment variable and no chat phrasing that raises any
# number in this block. The bridge enforces it, and ``audience_control.py``
# enforces it again independently, so a compromised or rogue bridge cannot
# exceed it either.
#
# WCAG 2.3.1's general flash threshold is more than three flashes in any one
# second. The strobe rate below sits at two, comfortably under it, and the
# burst is both short and rare.

#: Maximum flash rate of STROBE_BURST, in Hz.
STROBE_HZ_CAP = 2.0
#: Maximum duration of one STROBE_BURST, in seconds.
STROBE_MAX_S = 1.5
#: Minimum seconds between two STROBE_BURSTs.
STROBE_MIN_INTERVAL_S = 20.0
#: WHITEOUT is a single ramped flash, not a repeating one, so it is bounded by
#: duration and spacing alone.
WHITEOUT_MAX_S = 0.6
WHITEOUT_MIN_INTERVAL_S = 30.0
#: COLOR_POP carries no flash at all; it snaps a hue and holds it.
COLOR_POP_MAX_S = 2.0
COLOR_POP_MIN_INTERVAL_S = 8.0

#: One-shot -> (max duration, min interval). Consulted by both enforcement
#: points. Adding a one-shot without an entry here raises, by design.
ONESHOT_LIMITS: Dict[str, Tuple[float, float]] = {
    "STROBE_BURST": (STROBE_MAX_S, STROBE_MIN_INTERVAL_S),
    "WHITEOUT": (WHITEOUT_MAX_S, WHITEOUT_MIN_INTERVAL_S),
    "COLOR_POP": (COLOR_POP_MAX_S, COLOR_POP_MIN_INTERVAL_S),
}

# =============================================================================
# AUDIO -- there is none, and there must never be any
# =============================================================================
# The freeze lives in the audio chain. This process must never open an audio
# device, never synthesise speech, and never emit anything that could reach
# TouchDesigner's audio input. TTS (scope §5.2) is a separate, later, optional
# piece of work that routes to its own output device and its own OBS source.
#
# ``tests/test_chat_bridge.py::TestNoAudioPath`` scans this package's source
# for audio imports and asserts the rule rather than trusting this comment.
AUDIO_FORBIDDEN_IMPORTS: Tuple[str, ...] = (
    "sounddevice", "pyaudio", "simpleaudio", "playsound", "pydub",
    "elevenlabs", "pyttsx3", "gtts", "winsound", "afplay",
)

# --- Logging ------------------------------------------------------------------
LOG_PATH = os.environ.get(
    "CHAT_BRIDGE_LOG",
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "logs", "chat_bridge.ndjson"),
)

# --- YouTube quota ------------------------------------------------------------
#: Daily allocation for the whole Cloud project.
YT_QUOTA_DAILY = 10000
#: Stop polling here, leaving headroom for a rerun. The real per-call cost of
#: liveChatMessages.list is UNDOCUMENTED (scope §1.1) -- measure it off the
#: Cloud Console graph during the first stream and set YT_UNIT_COST to match.
YT_QUOTA_HARD_STOP = int(os.environ.get("CHAT_BRIDGE_QUOTA_STOP", "9000"))
YT_UNIT_COST = int(os.environ.get("CHAT_BRIDGE_UNIT_COST", "1"))
#: Never poll faster than this even if the API asks us to.
YT_MIN_POLL_S = 2.0
