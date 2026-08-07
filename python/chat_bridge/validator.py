"""GATE 2 -- plain-Python re-validation of whatever the model returned.

This is the gate that actually matters, because it does not trust the model at
all. It never reads a field it did not ask for, never coerces a type into
something usable, and resolves PROFILE targets against the LIVE registry
(``dj_graphics_profiles.PROFILES``) rather than against any list the prompt
happened to mention. If someone adds or removes a profile, this gate follows
automatically and the prompt cannot disagree with it.

Everything here is pure. A jailbroken interpreter, a malformed response, a
hostile chat line and a corrupted network packet all arrive at the same place:
``None``, plus a reason string for the log.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from . import config
from .model import Action, ChatMessage

#: A target must look like an enum member before it is even looked up. Cheap,
#: and it stops a lookup key that is 4 KB of shellcode from reaching the log.
_ENUM_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,31}$")


def valid_profile_targets() -> Tuple[str, ...]:
    """Read the profile whitelist from the live registry.

    Imported per call rather than at module load so the registry is genuinely
    the source of truth even if a profile is registered late.

    Returns:
        Registry keys, in registry order.
    """
    import dj_graphics_profiles as gp

    return tuple(gp.PROFILES.keys())


def all_targets() -> Tuple[str, ...]:
    """Every legal target across all verbs, for the interpreter's schema enum.

    Returns:
        Profile names + nudge targets + one-shot targets.
    """
    return valid_profile_targets() + config.NUDGE_TARGETS + config.ONESHOT_TARGETS


def _number(raw: Any, low: float, high: float, default: float) -> float:
    """Coerce a JSON value to a bounded float without ever trusting it.

    Three things this deliberately does NOT do:

    * Parse strings. A model returning ``"1e999"`` or ``"0x10"`` has been
      talked into something, and the right answer is the default, not a
      best-effort parse.
    * Accept booleans. ``True`` is an ``int`` in Python and would silently
      become an amount of 1.0.
    * Clamp non-finite values to a bound. ``NaN`` and ``inf`` fall back to the
      DEFAULT, not to the nearest limit -- clamping infinity to -1.0 would turn
      a nonsense value into a maximum-strength nudge in some direction, which
      is a worse failure than ignoring it.

    Args:
        raw: The value as it came out of JSON.
        low: Lower bound.
        high: Upper bound.
        default: Used when ``raw`` is absent, the wrong type, or not finite.

    Returns:
        A finite float within [low, high].
    """
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return default
    value = float(raw)
    if not math.isfinite(value):
        return default
    return max(low, min(high, value))


def validate_action(raw: Any,
                    batch: Sequence[ChatMessage]) -> Tuple[Optional[Action], str]:
    """Turn one model-emitted object into an Action, or refuse it.

    Refusal is the default. Every path that is not an explicit accept returns
    ``(None, reason)``.

    The author is resolved from the batch by INDEX, not by the name the model
    echoed back. The model therefore cannot invent an attribution, cannot put
    text of its own choosing on the acknowledgement overlay, and cannot dodge
    the per-user rate limiter by naming someone else.

    Args:
        raw: One element of the model's ``actions`` array. Any type.
        batch: The messages this call was given, in the order they were given.

    Returns:
        ``(Action, "ok")`` or ``(None, reason)``.
    """
    if not isinstance(raw, dict):
        return None, "not_an_object"

    verb = raw.get("verb")
    if not isinstance(verb, str) or verb not in config.VERBS:
        return None, "bad_verb"
    if verb == "NONE":
        return None, "none"

    target = raw.get("target")
    if not isinstance(target, str) or not _ENUM_RE.match(target):
        return None, "bad_target_shape"

    # Author resolution first: an action nobody can be held to is an action
    # that cannot be rate-limited, and that is a refusal, not a degradation.
    idx = raw.get("i")
    if isinstance(idx, bool) or not isinstance(idx, int):
        return None, "bad_index"
    if not 0 <= idx < len(batch):
        return None, "index_out_of_range"
    msg = batch[idx]

    confidence = _number(raw.get("confidence"), 0.0, 1.0, 0.0)
    if confidence < config.MIN_CONFIDENCE:
        return None, "low_confidence"

    action = Action(
        verb=verb,
        target=target,
        confidence=confidence,
        author_id=msg.author_id,
        safe_name=msg.safe_name,
    )

    if verb == "PROFILE":
        if target not in valid_profile_targets():
            return None, "unknown_profile"
        return action, "ok"

    if verb == "NUDGE":
        if target not in config.NUDGE_TARGETS:
            return None, "unknown_nudge"
        action.amount = _number(raw.get("amount"), config.NUDGE_MIN,
                                config.NUDGE_MAX, 0.0)
        if action.amount == 0.0:
            return None, "zero_nudge"
        return action, "ok"

    if verb == "ONESHOT":
        if target not in config.ONESHOT_TARGETS:
            return None, "unknown_oneshot"
        max_s, _interval = config.ONESHOT_LIMITS[target]
        # The model does not get to choose a duration at all. It gets the
        # ceiling, always, so a "duration": 600 in the response is not even a
        # near miss -- it is ignored.
        action.duration = max_s
        if target == "COLOR_POP":
            colour = raw.get("colour")
            if not isinstance(colour, str) or colour not in config.COLOUR_NAMES:
                return None, "unknown_colour"
            action.colour = colour
        return action, "ok"

    return None, "unreachable_verb"  # pragma: no cover - VERBS is exhaustive


def validate_response(payload: Any,
                      batch: Sequence[ChatMessage]
                      ) -> Tuple[List[Action], List[str]]:
    """Validate a whole interpreter response.

    A response that is not a dict with an ``actions`` list yields no actions.
    There is no partial-credit path and no repair attempt: malformed output is
    dropped, counted, and the show carries on with the look it already has.

    Args:
        payload: The parsed JSON object the interpreter returned.
        batch: The messages the interpreter was given.

    Returns:
        ``(accepted actions, rejection reasons)``. The reasons list is what
        goes in the NDJSON log, so a jailbreak attempt is visible after the
        fact rather than merely absent.
    """
    if not isinstance(payload, dict):
        return [], ["response_not_an_object"]
    actions = payload.get("actions")
    if not isinstance(actions, list):
        return [], ["response_missing_actions"]

    accepted: List[Action] = []
    reasons: List[str] = []
    # Bound the blast radius of a model that returns ten thousand actions.
    for raw in actions[: config.BATCH_MAX_LINES]:
        action, reason = validate_action(raw, batch)
        if action is None:
            reasons.append(reason)
        else:
            accepted.append(action)
    return accepted, reasons


def describe_vocabulary() -> Dict[str, Any]:
    """Snapshot the closed vocabularies, for the prompt and for the log.

    Returns:
        A dict of verb -> legal targets, read live.
    """
    return {
        "PROFILE": list(valid_profile_targets()),
        "NUDGE": list(config.NUDGE_TARGETS),
        "ONESHOT": list(config.ONESHOT_TARGETS),
        "COLOURS": list(config.COLOUR_NAMES),
    }
