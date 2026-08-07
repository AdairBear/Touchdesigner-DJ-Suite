"""The three data shapes that cross a stage boundary, and the name sanitizer.

Everything the audience typed lives in :class:`ChatMessage` and stays there.
:class:`Action` carries only enum members and clamped numbers, plus a display
name that has already been through :func:`safe_display_name`. That split is the
point: past the validator, no stage handles attacker-authored text at all.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

from . import config

#: What survives sanitization. Everything else is dropped, not escaped --
#: escaping implies the text is eventually un-escaped somewhere.
_NAME_ALLOWED = re.compile(r"[^A-Za-z0-9_.\-]")

#: Bidi overrides, zero-width joiners and the rest of the defacement toolkit.
#: Stripped before the whitelist as well, so a name is not silently truncated
#: into something that reads differently than it was typed.
_INVISIBLE = re.compile(
    "["
    "\u200b-\u200f"      # zero-width space .. RLM
    "\u202a-\u202e"      # bidi embedding + the RTL OVERRIDE
    "\u2060-\u2064"      # word joiner, invisible operators
    "\u2066-\u206f"      # bidi isolates, deprecated formatting
    "\ufeff"             # BOM used mid-string
    "]"
)


def strip_control(text: str) -> str:
    """Remove control, format and surrogate characters.

    Args:
        text: Arbitrary attacker-controlled text.

    Returns:
        The same text with every Unicode ``C*`` category character removed.
    """
    return "".join(ch for ch in text if unicodedata.category(ch)[0] != "C")


def combining_run_length(text: str) -> int:
    """Longest run of combining marks, i.e. how zalgo the text is.

    Args:
        text: Text to measure.

    Returns:
        The length of the longest consecutive run of ``Mn``/``Mc``/``Me``
        characters. Normal accented text has runs of 1, occasionally 2.
    """
    longest = run = 0
    for ch in text:
        if unicodedata.category(ch) in ("Mn", "Mc", "Me"):
            run += 1
            longest = max(longest, run)
        else:
            run = 0
    return longest


def safe_display_name(raw: Optional[str]) -> str:
    """Reduce a display name to something safe to put on a public broadcast.

    The name is attacker-controlled text headed for an on-screen overlay, so it
    is normalized (defeating homoglyph impersonation), stripped of invisibles
    and control characters (defeating zalgo and RTL-override defacement),
    whitelisted to a small character class, and truncated.

    Args:
        raw: The display name as the chat platform reported it.

    Returns:
        A name matching ``[A-Za-z0-9_.-]{0,20}``. May be empty, which callers
        must treat as "no name to acknowledge" rather than substituting one.
    """
    if not raw:
        return ""
    text = unicodedata.normalize("NFKC", str(raw))
    text = _INVISIBLE.sub("", text)
    text = strip_control(text)
    text = _NAME_ALLOWED.sub("", text)
    return text[: config.NAME_MAX_LEN]


@dataclass
class ChatMessage:
    """One line of chat, normalized across sources.

    Attributes:
        msg_id: Platform message id, used only for dedupe.
        author_id: Stable per-viewer id, used for the per-user limiters. Falls
            back to the raw display name when a source has no id.
        author_name: Raw display name. Attacker-controlled; never rendered.
        safe_name: Sanitized name, the only form allowed near an overlay.
        text: Raw message text. Attacker-controlled; only ever passed to the
            moderation and interpreter APIs as data, never as instruction.
        ts: Monotonic receipt time, not platform time -- every limiter in the
            bridge compares against the same clock.
        source: Which ChatSource produced it, for weighting and logging.
    """

    msg_id: str
    author_id: str
    author_name: str
    text: str
    ts: float
    source: str = "youtube"
    safe_name: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.safe_name = safe_display_name(self.author_name)
        self.text = self.text[: config.TEXT_MAX_LEN]


@dataclass
class Action:
    """A validated instruction. Every field is an enum member or a clamped float.

    An Action can only be constructed by :mod:`chat_bridge.validator`, which is
    the gate that does not trust the model at all.

    Attributes:
        verb: One of ``PROFILE`` / ``NUDGE`` / ``ONESHOT``. ``NONE`` never
            becomes an Action -- it is discarded at validation.
        target: A member of the enum matching ``verb``. For ``PROFILE`` this is
            a key present in the LIVE ``dj_graphics_profiles.PROFILES``.
        amount: Clamped to [-1, 1]. Meaningful for ``NUDGE`` only.
        colour: A named neon anchor, for ``ONESHOT COLOR_POP`` only.
        duration: Seconds, already clamped to the photosensitivity ceiling.
        confidence: The interpreter's own 0..1 score, post-clamp.
        author_id: Who asked, for the per-user limiters.
        safe_name: Sanitized name for the acknowledgement overlay.
    """

    verb: str
    target: str
    amount: float = 0.0
    colour: Optional[str] = None
    duration: float = 0.0
    confidence: float = 1.0
    author_id: str = ""
    safe_name: str = ""

    def key(self) -> str:
        """Vote-bucket key.

        Returns:
            ``"VERB:TARGET"``, the granularity the tally counts at.
        """
        return "%s:%s" % (self.verb, self.target)


@dataclass
class Decision:
    """One resolved thing to send, after arbitration.

    Attributes:
        verb: As :class:`Action`.
        target: As :class:`Action`.
        amount: Post-tally, post-gain, post-clamp scalar.
        colour: Named anchor or None.
        duration: Post-ceiling seconds.
        votes: How many distinct viewers asked for this.
        safe_name: The earliest requester's sanitized name, for the ack.
    """

    verb: str
    target: str
    amount: float = 0.0
    colour: Optional[str] = None
    duration: float = 0.0
    votes: int = 1
    safe_name: str = ""
