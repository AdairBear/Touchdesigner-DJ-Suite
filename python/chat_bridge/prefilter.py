"""The cheap gate in front of the expensive one.

Most chat is not a request. Sending "tuuuune", "hi from brazil" and six fire
emoji to a language model costs money and adds latency for a guaranteed NONE,
so a keyword screen runs first and only survivors are batched.

This is a COST filter, not a SAFETY filter. It is deliberately permissive --
letting a hostile line through costs nothing, because the gates that matter are
downstream. It never rejects on content, only on "contains no word that could
possibly be a visual request".
"""

from __future__ import annotations

import re
from typing import Iterable, List, Sequence

from .model import ChatMessage

#: Words that could plausibly begin a visual request. Generous on purpose: a
#: false positive costs a few tokens, a false negative costs a viewer their
#: moment. Sorted by theme rather than alphabetically so it stays readable when
#: it is inevitably extended after the first show.
_KEYWORDS = (
    # looks / profiles
    "profile", "look", "mode", "vibe", "style", "preset", "switch", "change",
    "rave", "laser", "strobe", "acid", "vapor", "vapour", "mono", "uv",
    "pulse", "deep",
    # qualities / nudges
    "glow", "bright", "dark", "dim", "flash", "trail", "smear", "shake",
    "wobble", "zoom", "punch", "speed", "fast", "slow", "faster", "slower",
    "more", "less", "harder", "softer", "bigger", "smaller", "intense",
    "chill", "calm", "crazy", "insane", "wild",
    # one-shots
    "burst", "pop", "whiteout", "white", "blast", "drop", "hit",
    # colours
    "colour", "color", "cyan", "magenta", "green", "pink", "purple", "violet",
    "blue", "red", "orange", "yellow", "neon",
    # verbs people actually type
    "make", "give", "turn", "put", "go", "want", "need", "please", "pls",
    "can", "could", "do", "add", "bring",
)

_WORD = re.compile(r"[a-z]+")


def looks_like_request(text: str) -> bool:
    """Report whether a line is worth spending a model call on.

    Args:
        text: The raw message text.

    Returns:
        True if any keyword appears as a whole word.
    """
    words = set(_WORD.findall(text.lower()))
    if not words:
        return False
    return any(word in words for word in _KEYWORDS)


def prefilter(messages: Iterable[ChatMessage]) -> List[ChatMessage]:
    """Keep only the messages that could be requests.

    Args:
        messages: Candidate messages.

    Returns:
        The subset worth batching, order preserved.
    """
    return [m for m in messages if looks_like_request(m.text)]


def dedupe(messages: Sequence[ChatMessage]) -> List[ChatMessage]:
    """Drop repeats of the same text from the same author within a batch.

    Copy-paste spam is the common case and it would otherwise inflate a vote
    tally with one person's enthusiasm.

    Args:
        messages: Candidate messages.

    Returns:
        The first occurrence of each ``(author_id, text)`` pair.
    """
    seen = set()
    out: List[ChatMessage] = []
    for msg in messages:
        key = (msg.author_id, " ".join(msg.text.split()).lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(msg)
    return out
