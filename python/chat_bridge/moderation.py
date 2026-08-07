"""Moderation, which fails CLOSED.

The threat model here is narrower than it looks. Abusive text cannot produce
abusive visuals -- the action space is a closed enum of five pre-validated
looks, so a slur maps to NONE or to a look Thomas already approved. What
moderation actually protects is the acknowledgement overlay: the one path where
audience-authored characters reach the broadcast.

Three layers, cheapest first: the platform's own moderation (free, upstream and
outside this file), a structural/local screen, and OpenAI's moderation
endpoint, which is free and therefore runs on every message rather than only on
the ones that would be rendered.

FAIL-LOUD: a moderation call that errors or times out is a FAILED check, never
a passed one -- an outage must not become an open microphone. Consecutive
failures raise an operator alert through a callback that is independent of the
moderation transport itself, so the alarm does not ride the path it watches.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence, Tuple

from . import config
from .model import ChatMessage, combining_run_length, strip_control

#: Structural rejects, before any network call. Not a slur list -- that belongs
#: upstream in the platform's own moderation, which sees far more traffic and
#: is maintained by someone else. This catches the shapes that break rendering.
MAX_COMBINING_RUN = 2


class ModerationResult:
    """Outcome of one check.

    Attributes:
        ok: True only when the message passed every layer that ran.
        reason: Machine-readable reason when it did not.
        errored: True when a layer failed rather than rejected. Distinguishing
            these matters: rejection is the system working, error is the system
            blind, and only the second one should page anybody.
    """

    def __init__(self, ok: bool, reason: str = "ok", errored: bool = False) -> None:
        self.ok = ok
        self.reason = reason
        self.errored = errored

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return "<ModerationResult ok=%s reason=%s>" % (self.ok, self.reason)


def structural_check(msg: ChatMessage) -> ModerationResult:
    """Local screen: shapes that are hostile regardless of what they say.

    Args:
        msg: The message to screen.

    Returns:
        A result. Never errors, never calls out.
    """
    if len(msg.text) > config.TEXT_MAX_LEN:
        return ModerationResult(False, "text_too_long")
    if combining_run_length(msg.author_name) > MAX_COMBINING_RUN:
        return ModerationResult(False, "zalgo_name")
    if combining_run_length(msg.text) > MAX_COMBINING_RUN:
        return ModerationResult(False, "zalgo_text")
    if strip_control(msg.author_name) != msg.author_name:
        return ModerationResult(False, "control_chars_in_name")
    if not msg.safe_name:
        # A name that sanitizes to nothing cannot be acknowledged on screen,
        # and an un-acknowledgeable request is not worth acting on.
        return ModerationResult(False, "name_unrenderable")
    return ModerationResult(True)


class Moderator:
    """Runs the local screen, then the hosted one, and fails closed on both.

    Args:
        moderate_fn: ``(texts) -> list[bool]`` returning True for each text
            that is ACCEPTABLE. Injected in tests; defaults to OpenAI.
        alert_fn: Called with a message when consecutive failures cross the
            threshold. Must not use the same transport as ``moderate_fn``.
        enabled: False skips the hosted layer entirely -- for offline replay
            only, and it logs as such.
    """

    def __init__(self, moderate_fn: Optional[Callable[[Sequence[str]], List[bool]]] = None,
                 alert_fn: Optional[Callable[[str], None]] = None,
                 enabled: bool = True) -> None:
        self._moderate = moderate_fn or _openai_moderation
        self._alert = alert_fn or (lambda msg: None)
        self.enabled = enabled
        self.consecutive_failures = 0
        self.total_rejected = 0
        self.total_errored = 0

    def check_batch(self, messages: Sequence[ChatMessage]
                    ) -> Tuple[List[ChatMessage], List[Tuple[str, str]]]:
        """Screen a batch, returning survivors and per-message rejections.

        Both the message text and the display name are submitted, because the
        name is the payload in the overlay attack.

        Args:
            messages: Candidates.

        Returns:
            ``(passed, [(author_id, reason), ...])``.
        """
        rejected: List[Tuple[str, str]] = []
        local_pass: List[ChatMessage] = []
        for msg in messages:
            result = structural_check(msg)
            if result.ok:
                local_pass.append(msg)
            else:
                rejected.append((msg.author_id, result.reason))
        if not local_pass:
            return [], rejected
        if not self.enabled:
            return local_pass, rejected

        # One call for the whole batch: name and text interleaved so a single
        # response covers both, and a per-index verdict maps back cleanly.
        payload: List[str] = []
        for msg in local_pass:
            payload.append(msg.text)
            payload.append(msg.author_name)

        try:
            verdicts = self._moderate(payload)
            if len(verdicts) != len(payload):
                raise ValueError("moderation returned %d verdicts for %d inputs"
                                 % (len(verdicts), len(payload)))
        except Exception as exc:  # noqa: BLE001 - deliberate: fail closed, loudly
            self.consecutive_failures += 1
            self.total_errored += len(local_pass)
            if self.consecutive_failures >= config.MODERATION_ALERT_AFTER:
                self._alert(
                    "moderation has failed %d times in a row (%s: %s) -- every "
                    "message is being dropped until it recovers"
                    % (self.consecutive_failures, type(exc).__name__, exc))
            return [], rejected + [(m.author_id, "moderation_error")
                                   for m in local_pass]

        self.consecutive_failures = 0
        passed: List[ChatMessage] = []
        for i, msg in enumerate(local_pass):
            if verdicts[2 * i] and verdicts[2 * i + 1]:
                passed.append(msg)
            else:
                reason = "flagged_text" if not verdicts[2 * i] else "flagged_name"
                rejected.append((msg.author_id, reason))
                self.total_rejected += 1
        return passed, rejected


def _openai_moderation(texts: Sequence[str]) -> List[bool]:
    """Default hosted layer: one omni-moderation call for the batch.

    Args:
        texts: Strings to screen.

    Returns:
        True per input that is acceptable.

    Raises:
        RuntimeError: If the OpenAI SDK is not installed.
        Exception: Anything the SDK raises. Callers fail closed on it.
    """
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - depends on the venv
        raise RuntimeError(
            "openai not installed; pip install -r requirements-chat.txt") from exc

    client = OpenAI(timeout=config.MODERATION_TIMEOUT_S)
    response = client.moderations.create(
        model=config.MODERATION_MODEL, input=list(texts))
    return [not _flagged(result) for result in response.results]


def _flagged(result: Any) -> bool:
    """Read the flag off a moderation result object or dict.

    Args:
        result: One element of the SDK's ``results``.

    Returns:
        True if the input was flagged.
    """
    if isinstance(result, dict):
        return bool(result.get("flagged"))
    return bool(getattr(result, "flagged", True))
