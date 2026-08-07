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

from . import config  # noqa: F401
from .arbiter import Arbiter, Intake  # noqa: F401
from .bridge import ChatBridge, NdjsonLog  # noqa: F401
from .emitter import Emitter, decision_to_osc  # noqa: F401
from .interpreter import Interpreter  # noqa: F401
from .moderation import Moderator  # noqa: F401
from .model import Action, ChatMessage, Decision, safe_display_name  # noqa: F401
from .validator import validate_action, validate_response  # noqa: F401

__all__ = [
    "Action", "Arbiter", "ChatBridge", "ChatMessage", "Decision", "Emitter",
    "Intake", "Interpreter", "Moderator", "NdjsonLog", "config",
    "decision_to_osc", "safe_display_name", "validate_action",
    "validate_response",
]
