"""Flow control: five limiters, a vote window, and the ceiling nobody can vote away.

Why a WINDOW and not a QUEUE. A FIFO queue with a cooldown converts a burst into
a slow drip of stale requests -- at minute three the rig would still be
executing minute one's chat. Tallying discards staleness for free: a hundred
messages in thirty seconds become one visual change that reflects what the room
actually wants, and the losing buckets are dropped rather than deferred.

Every method takes ``now`` explicitly. No clock is read inside this module, so
every limiter, cooldown and ceiling is deterministic under test at any time
scale, including the ones that only bite after twenty minutes.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Dict, List, Optional, Set, Tuple

from . import config
from .model import Action, Decision


class Intake:
    """Bounded, rate-capped front door.

    A raid must be able to exhaust neither memory nor the LLM budget, so the
    queue has a hard length and the admission rate has a hard ceiling. Both
    drop the OLDEST, because in a burst the newest messages are the ones that
    still reflect what the room is asking for.

    Args:
        max_len: Queue capacity.
        max_per_s: Admissions per second.
    """

    def __init__(self, max_len: int = config.INTAKE_QUEUE_MAX,
                 max_per_s: float = config.INTAKE_MAX_PER_S) -> None:
        self._queue: Deque = deque(maxlen=max_len)
        self._admissions: Deque[float] = deque()
        self.max_per_s = max_per_s
        self.dropped_rate = 0
        self.dropped_overflow = 0
        self.seen_ids: Deque[str] = deque(maxlen=max_len * 4)
        self._seen: Set[str] = set()

    def offer(self, msg, now: float) -> bool:
        """Admit a message, or drop it.

        Args:
            msg: A :class:`~chat_bridge.model.ChatMessage`.
            now: Monotonic seconds.

        Returns:
            True if admitted.
        """
        if msg.msg_id and msg.msg_id in self._seen:
            return False
        while self._admissions and now - self._admissions[0] > 1.0:
            self._admissions.popleft()
        if len(self._admissions) >= self.max_per_s:
            self.dropped_rate += 1
            return False
        if len(self._queue) == self._queue.maxlen:
            self.dropped_overflow += 1
        if msg.msg_id:
            if len(self.seen_ids) == self.seen_ids.maxlen and self.seen_ids:
                self._seen.discard(self.seen_ids[0])
            self.seen_ids.append(msg.msg_id)
            self._seen.add(msg.msg_id)
        self._admissions.append(now)
        self._queue.append(msg)
        return True

    def drain(self) -> List:
        """Take everything queued.

        Returns:
            The queued messages, oldest first. The queue is left empty.
        """
        out = list(self._queue)
        self._queue.clear()
        return out

    def __len__(self) -> int:
        return len(self._queue)


class _Bucket:
    """One (verb, target) tally within the current window."""

    def __init__(self, action: Action, now: float) -> None:
        self.verb = action.verb
        self.target = action.target
        self.voters: Set[str] = set()
        self.total_amount = 0.0
        self.first_seen = now
        self.first_name = action.safe_name
        self.colour: Optional[str] = action.colour

    def add(self, action: Action) -> None:
        """Fold one action into the tally.

        Args:
            action: A validated action for this bucket.
        """
        self.voters.add(action.author_id)
        self.total_amount += action.amount

    @property
    def votes(self) -> int:
        """Distinct viewers who asked for this.

        Returns:
            Voter count -- distinct, so copy-pasting does not count twice.
        """
        return len(self.voters)


class Arbiter:
    """Decides what, if anything, the audience gets to change.

    Attributes:
        enabled: The bridge-side half of the kill switch. The TD-side half is
            independent, so a hung or rogue bridge still cannot get through.
        gain: Global scale on every audience-driven scalar. 0.3 is "they can
            tint it"; 1.0 is "they're driving". A dial, not a switch.
        lock_profile: Audience keeps NUDGE and ONESHOT, loses PROFILE votes.
        lockout_until: While ``now`` is below this, audience actions are
            received, tallied and logged -- and not applied.
    """

    def __init__(self) -> None:
        self.enabled = True
        self.gain = 1.0
        self.lock_profile = False
        self.lockout_until = 0.0

        self._buckets: Dict[str, _Bucket] = {}
        self._window_start = 0.0
        self._user_last: Dict[str, float] = {}
        self._user_count: Dict[str, int] = {}
        self._verb_last: Dict[str, float] = {}
        self._oneshot_last: Dict[str, float] = {}
        self._pending_oneshots: List[Action] = []

        self.counters: Dict[str, int] = {}

    # --- operator control ----------------------------------------------------

    def arm_lockout(self, now: float,
                    seconds: float = config.OPERATOR_LOCKOUT_S) -> None:
        """Give Thomas the room for a while.

        A timer rather than a mode, so it self-clears and he never has to
        remember to re-enable anything.

        Args:
            now: Monotonic seconds.
            seconds: Lockout length.
        """
        self.lockout_until = max(self.lockout_until, now + seconds)

    def panic(self, now: float) -> None:
        """Clear the vote window and hold the audience off for five minutes.

        PANIC means something went wrong, so it holds longer than an ordinary
        override and it discards pending votes rather than deferring them.

        Args:
            now: Monotonic seconds.
        """
        self._buckets.clear()
        self._pending_oneshots.clear()
        self.arm_lockout(now, config.PANIC_LOCKOUT_S)

    def locked_out(self, now: float) -> bool:
        """Report whether Thomas currently owns the look.

        Args:
            now: Monotonic seconds.

        Returns:
            True while his lockout is running.
        """
        return now < self.lockout_until

    # --- intake --------------------------------------------------------------

    def _count(self, reason: str) -> None:
        self.counters[reason] = self.counters.get(reason, 0) + 1

    def offer(self, action: Action, now: float) -> str:
        """Apply the per-user limiters and tally the action.

        Args:
            action: A validated action.
            now: Monotonic seconds.

        Returns:
            ``"accepted"``, or the name of the limiter that refused it.
        """
        last = self._user_last.get(action.author_id)
        if last is not None and now - last < config.PER_USER_COOLDOWN_S:
            self._count("per_user_cooldown")
            return "per_user_cooldown"
        if self._user_count.get(action.author_id, 0) >= config.PER_USER_DAILY_CAP:
            self._count("per_user_cap")
            return "per_user_cap"
        if action.verb == "PROFILE" and self.lock_profile:
            self._count("profile_locked")
            return "profile_locked"

        self._user_last[action.author_id] = now
        self._user_count[action.author_id] = \
            self._user_count.get(action.author_id, 0) + 1
        self._count("accepted")

        if action.verb == "ONESHOT":
            # One-shots bypass the vote: a burst under two seconds is
            # low-stakes and immediacy is the whole appeal. They still obey
            # their own cooldown and the photosensitivity ceiling.
            self._pending_oneshots.append(action)
            return "accepted"

        if not self._buckets:
            self._window_start = now
        bucket = self._buckets.get(action.key())
        if bucket is None:
            bucket = _Bucket(action, now)
            self._buckets[action.key()] = bucket
        bucket.add(action)
        return "accepted"

    # --- resolution ----------------------------------------------------------

    def window_due(self, now: float) -> bool:
        """Report whether the vote window has closed.

        Args:
            now: Monotonic seconds.

        Returns:
            True when there is a tally and the window has elapsed.
        """
        return bool(self._buckets) and now - self._window_start >= config.VOTE_WINDOW_S

    def take_oneshots(self, now: float) -> List[Decision]:
        """Drain any one-shot that clears its cooldown and the ceiling.

        Args:
            now: Monotonic seconds.

        Returns:
            Zero or more decisions, in request order.
        """
        out: List[Decision] = []
        pending, self._pending_oneshots = self._pending_oneshots, []
        if not self.enabled:
            self._count("suppressed_disabled")
            return []
        if self.locked_out(now):
            self._count("suppressed_lockout")
            return []
        for action in pending:
            if not self._emit_allowed(action.verb, now):
                self._count("cooldown_%s" % action.verb)
                continue
            allowed, duration = self.ceiling_for(action.target, now)
            if not allowed:
                self._count("ceiling_%s" % action.target)
                continue
            self._verb_last[action.verb] = now
            self._oneshot_last[action.target] = now
            out.append(Decision(
                verb=action.verb, target=action.target, duration=duration,
                colour=action.colour, votes=1, safe_name=action.safe_name,
            ))
        return out

    def resolve(self, now: float) -> Tuple[List[Decision], Dict[str, int]]:
        """Close the window and return at most one PROFILE plus the nudges.

        The tally is computed and returned as ``tally`` even when nothing is
        emitted, so the log shows what the room asked for during a lockout
        rather than showing silence.

        Args:
            now: Monotonic seconds.

        Returns:
            ``(decisions, tally)``. ``decisions`` is empty while disabled or
            locked out.
        """
        buckets = list(self._buckets.values())
        self._buckets = {}
        tally = {"%s:%s" % (b.verb, b.target): b.votes for b in buckets}
        if not buckets:
            return [], tally

        decisions: List[Decision] = []

        profiles = [b for b in buckets if b.verb == "PROFILE"
                    and b.votes >= config.PROFILE_QUORUM]
        if profiles:
            # Most votes wins; a tie goes to whoever asked first, so the room's
            # earliest expressed wish breaks it rather than dict ordering.
            profiles.sort(key=lambda b: (-b.votes, b.first_seen))
            winner = profiles[0]
            if self._emit_allowed("PROFILE", now):
                decisions.append(Decision(
                    verb="PROFILE", target=winner.target, votes=winner.votes,
                    safe_name=winner.first_name,
                ))
            else:
                self._count("cooldown_PROFILE")
        elif any(b.verb == "PROFILE" for b in buckets):
            self._count("no_quorum")

        # Same-target nudges SUM then clamp -- five people asking for more glow
        # is a bigger nudge, up to the cap, rather than five competing votes.
        for bucket in sorted((b for b in buckets if b.verb == "NUDGE"),
                             key=lambda b: b.first_seen):
            if not self._emit_allowed("NUDGE", now):
                self._count("cooldown_NUDGE")
                break
            amount = max(config.NUDGE_MIN,
                         min(config.NUDGE_MAX, bucket.total_amount))
            decisions.append(Decision(
                verb="NUDGE", target=bucket.target, amount=amount,
                votes=bucket.votes, safe_name=bucket.first_name,
            ))

        if not self.enabled:
            self._count("suppressed_disabled")
            return [], tally
        if self.locked_out(now):
            self._count("suppressed_lockout")
            return [], tally

        # Stamp the cooldowns only for what is actually emitted, so a
        # suppressed window does not silently consume the next one's budget.
        for decision in decisions:
            self._verb_last[decision.verb] = now
            if decision.verb == "NUDGE":
                decision.amount = self._apply_gain(decision.amount)
        return [d for d in decisions
                if d.verb != "NUDGE" or d.amount != 0.0], tally

    def _apply_gain(self, amount: float) -> float:
        """Scale a scalar by the operator's intensity dial and re-clamp.

        Args:
            amount: Post-tally scalar.

        Returns:
            The scaled, clamped scalar.
        """
        scaled = amount * max(0.0, min(1.0, self.gain))
        return max(config.NUDGE_MIN, min(config.NUDGE_MAX, scaled))

    def _emit_allowed(self, verb: str, now: float) -> bool:
        """Check the global per-verb cooldown, the thrash guard.

        Args:
            verb: ``PROFILE`` / ``NUDGE`` / ``ONESHOT``.
            now: Monotonic seconds.

        Returns:
            True if enough time has passed since the last emission of it.
        """
        last = self._verb_last.get(verb)
        if last is None:
            return True
        return now - last >= config.ACTION_COOLDOWN_S[verb]

    # =========================================================================
    # THE CEILING. Not a limiter -- limiters are tunable, this is not.
    # =========================================================================

    def ceiling_for(self, target: str, now: float) -> Tuple[bool, float]:
        """Apply the photosensitivity ceiling to a one-shot.

        There is no argument, address, vote, gain setting or chat phrasing that
        relaxes this. It is enforced again, independently, inside
        ``audience_control.py``, so a compromised bridge cannot exceed it
        either.

        Args:
            target: A one-shot target.
            now: Monotonic seconds.

        Returns:
            ``(allowed, duration_seconds)``. The duration is the CEILING, not a
            request -- nothing upstream gets to choose it.
        """
        limits = config.ONESHOT_LIMITS.get(target)
        if limits is None:
            return False, 0.0
        max_s, min_interval = limits
        last = self._oneshot_last.get(target)
        if last is not None and now - last < min_interval:
            return False, 0.0
        return True, max_s
