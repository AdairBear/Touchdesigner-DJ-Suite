"""Audience-interactive chat -> graphics bridge.

A third external OSC producer alongside ``movement_tracker.py`` and TouchOSC.
It reads live chat, moderates it, batches it into schema-constrained model
calls that can only emit members of a closed enum, tallies those into about one
decision every thirty seconds, and pushes the result through the same OSC
whitelist the TouchOSC buttons already use.

The one architectural sentence: **the audience never touches TouchDesigner, the
audience votes on an enum.** Everything in this package is machinery in service
of that.

No audio device is ever opened here, and no network call runs on TouchDesigner's
cook thread.

Run it with ``python -m chat_bridge --help`` from the repo's ``python/``
directory. See ``docs/audience_chat_bridge_runbook.md``.
"""

from __future__ import annotations

import os
import sys

# --- The profile registry has to be importable, or GATE 2 has no whitelist ---
# `validator.valid_profile_targets` imports `dj_graphics_profiles`, which lives
# in touchdesigner/scripts/ and is NOT on the path when this package is run the
# documented way (`python -m chat_bridge` from python/). Nothing here put it
# there, so that import raised ModuleNotFoundError inside
# `Interpreter.classify`'s try block -- which caught it, counted it as
# `interpreter_error`, and dropped the batch.
#
# Every batch. For the whole run. The bridge would poll chat, moderate it,
# heartbeat cleanly, and emit exactly nothing, while the log blamed the model.
# That is the silent-failure shape `~/.claude/rules/fail-loud-observability.md`
# exists to forbid, and it survived 735 unit tests because the tests put
# touchdesigner/scripts on sys.path themselves.
#
# Prepending is deliberate: the registry TouchDesigner runs must be the one this
# validates against, and a same-named module further down a path is a whitelist
# that silently disagrees with the show.
_SCRIPTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "touchdesigner", "scripts")
if os.path.isdir(_SCRIPTS) and _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from . import config  # noqa: F401,E402
from .arbiter import Arbiter, Intake  # noqa: F401,E402
from .bridge import ChatBridge, NdjsonLog  # noqa: F401,E402
from .emitter import Emitter, decision_to_osc  # noqa: F401,E402
from .interpreter import Interpreter  # noqa: F401,E402
from .moderation import Moderator  # noqa: F401,E402
from .model import Action, ChatMessage, Decision, safe_display_name  # noqa: F401,E402
from .validator import validate_action, validate_response  # noqa: F401,E402

__all__ = [
    "Action", "Arbiter", "ChatBridge", "ChatMessage", "Decision", "Emitter",
    "Intake", "Interpreter", "Moderator", "NdjsonLog", "config",
    "decision_to_osc", "safe_display_name", "validate_action",
    "validate_response",
]
