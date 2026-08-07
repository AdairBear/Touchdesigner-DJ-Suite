"""Offline tests for flow control: the five limiters, the vote window, the
override, and the ceiling the audience cannot vote away.

Every method on the Arbiter takes ``now`` explicitly, so none of these tests
sleep. A twenty-minute strobe-spacing rule is exercised in microseconds, which
is the only way a limit that only bites after twenty minutes ever gets tested
at all.

The scenario that motivates the whole module -- "100 messages in 5 seconds" --
is the first test in TestVoteWindow.

Run:  ./venv/bin/python -m pytest tests/test_chat_arbiter.py -v
"""

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "touchdesigner" / "scripts"))
sys.path.insert(0, str(REPO / "python"))

import dj_graphics_profiles as gp  # noqa: E402
from chat_bridge import config  # noqa: E402
from chat_bridge.arbiter import Arbiter  # noqa: E402
from chat_bridge.model import Action  # noqa: E402

FIRST, SECOND = list(gp.PROFILES)[0], list(gp.PROFILES)[1]


def profile_action(target, author):
    """Build a PROFILE action.

    Args:
        target: Registry key.
        author: Author id.

    Returns:
        An Action.
    """
    return Action(verb="PROFILE", target=target, author_id=author,
                  safe_name=author)


def nudge(target, amount, author):
    """Build a NUDGE action.

    Args:
        target: Nudge target.
        amount: Scalar in [-1, 1].
        author: Author id.

    Returns:
        An Action.
    """
    return Action(verb="NUDGE", target=target, amount=amount,
                  author_id=author, safe_name=author)


def oneshot(target, author, colour=None):
    """Build a ONESHOT action carrying the ceiling duration.

    Args:
        target: One-shot target.
        author: Author id.
        colour: Named anchor, for COLOR_POP.

    Returns:
        An Action.
    """
    return Action(verb="ONESHOT", target=target, author_id=author,
                  safe_name=author, colour=colour,
                  duration=config.ONESHOT_LIMITS[target][0])


class TestVoteWindow:
    def test_one_hundred_messages_in_five_seconds_produce_one_change(self):
        """The headline requirement, stated exactly as the design states it."""
        arbiter = Arbiter()
        for i in range(100):
            arbiter.offer(profile_action(SECOND, "viewer%d" % i), i * 0.05)
        decisions, tally = arbiter.resolve(config.VOTE_WINDOW_S)
        assert len(decisions) == 1
        assert decisions[0].target == SECOND
        assert tally["PROFILE:%s" % SECOND] == 100

    def test_the_room_gets_what_most_of_it_asked_for(self):
        arbiter = Arbiter()
        for i in range(3):
            arbiter.offer(profile_action(FIRST, "a%d" % i), 0.0)
        for i in range(7):
            arbiter.offer(profile_action(SECOND, "b%d" % i), 1.0)
        decisions, _ = arbiter.resolve(config.VOTE_WINDOW_S)
        assert [d.target for d in decisions] == [SECOND]

    def test_a_tie_goes_to_whoever_asked_first(self):
        arbiter = Arbiter()
        arbiter.offer(profile_action(SECOND, "early1"), 0.0)
        arbiter.offer(profile_action(SECOND, "early2"), 0.1)
        arbiter.offer(profile_action(FIRST, "late1"), 5.0)
        arbiter.offer(profile_action(FIRST, "late2"), 5.1)
        decisions, _ = arbiter.resolve(config.VOTE_WINDOW_S)
        assert decisions[0].target == SECOND

    def test_losing_buckets_are_dropped_not_deferred(self):
        """A queue would replay minute one's chat during minute three."""
        arbiter = Arbiter()
        for i in range(2):
            arbiter.offer(profile_action(FIRST, "a%d" % i), 0.0)
        for i in range(5):
            arbiter.offer(profile_action(SECOND, "b%d" % i), 0.0)
        arbiter.resolve(config.VOTE_WINDOW_S)
        later, tally = arbiter.resolve(config.VOTE_WINDOW_S * 4)
        assert later == [] and tally == {}

    def test_one_viewer_cannot_flip_the_whole_look(self):
        arbiter = Arbiter()
        arbiter.offer(profile_action(SECOND, "solo"), 0.0)
        decisions, tally = arbiter.resolve(config.VOTE_WINDOW_S)
        assert decisions == []
        assert tally["PROFILE:%s" % SECOND] == 1
        assert arbiter.counters.get("no_quorum") == 1

    def test_a_single_viewer_stream_still_gets_nudges_and_oneshots(self):
        """Degrading to 'nudges only' is the right behaviour, not an outage."""
        arbiter = Arbiter()
        arbiter.offer(nudge("GLOW", 0.5, "solo"), 0.0)
        decisions, _ = arbiter.resolve(config.VOTE_WINDOW_S)
        assert [d.target for d in decisions] == ["GLOW"]

    def test_copy_pasting_does_not_count_as_two_voters(self):
        arbiter = Arbiter()
        arbiter.offer(profile_action(SECOND, "spammer"), 0.0)
        # Same author again, far enough out that the per-user cooldown allows it.
        arbiter.offer(profile_action(SECOND, "spammer"),
                      config.PER_USER_COOLDOWN_S + 1)
        _, tally = arbiter.resolve(config.PER_USER_COOLDOWN_S + config.VOTE_WINDOW_S)
        assert tally["PROFILE:%s" % SECOND] == 1, "votes are distinct viewers"

    def test_window_is_not_due_until_it_elapses(self):
        arbiter = Arbiter()
        arbiter.offer(nudge("GLOW", 0.4, "a"), 0.0)
        assert arbiter.window_due(config.VOTE_WINDOW_S - 0.1) is False
        assert arbiter.window_due(config.VOTE_WINDOW_S) is True

    def test_an_empty_window_is_never_due(self):
        assert Arbiter().window_due(1e6) is False


class TestNudgeAccumulation:
    def test_same_target_nudges_sum(self):
        arbiter = Arbiter()
        for i in range(3):
            arbiter.offer(nudge("GLOW", 0.2, "u%d" % i), 0.0)
        decisions, _ = arbiter.resolve(config.VOTE_WINDOW_S)
        assert decisions[0].amount == pytest.approx(0.6)

    def test_the_sum_is_clamped(self):
        arbiter = Arbiter()
        for i in range(50):
            arbiter.offer(nudge("GLOW", 1.0, "u%d" % i), 0.0)
        decisions, _ = arbiter.resolve(config.VOTE_WINDOW_S)
        assert decisions[0].amount == config.NUDGE_MAX

    def test_opposing_nudges_cancel_rather_than_compete(self):
        arbiter = Arbiter()
        arbiter.offer(nudge("GLOW", 0.6, "more"), 0.0)
        arbiter.offer(nudge("GLOW", -0.6, "less"), 0.0)
        decisions, _ = arbiter.resolve(config.VOTE_WINDOW_S)
        assert decisions == [], "a net-zero nudge is not worth a packet"

    def test_different_nudge_targets_all_emit(self):
        arbiter = Arbiter()
        arbiter.offer(nudge("GLOW", 0.5, "a"), 0.0)
        arbiter.offer(nudge("ZOOM", -0.5, "b"), 0.0)
        decisions, _ = arbiter.resolve(config.VOTE_WINDOW_S)
        assert {d.target for d in decisions} == {"GLOW", "ZOOM"}


class TestPerUserLimiters:
    def test_per_user_cooldown_holds(self):
        arbiter = Arbiter()
        assert arbiter.offer(nudge("GLOW", 0.5, "keen"), 0.0) == "accepted"
        assert arbiter.offer(nudge("GLOW", 0.5, "keen"), 10.0) == "per_user_cooldown"
        assert arbiter.offer(nudge("GLOW", 0.5, "keen"),
                             config.PER_USER_COOLDOWN_S) == "accepted"

    def test_one_viewer_cannot_drive_the_show(self):
        arbiter = Arbiter()
        accepted = sum(arbiter.offer(nudge("GLOW", 1.0, "keen"), t * 0.5) == "accepted"
                       for t in range(200))
        assert accepted == 2, "100 seconds of spam buys exactly two requests"

    def test_per_user_daily_cap(self):
        arbiter = Arbiter()
        now = 0.0
        for _ in range(config.PER_USER_DAILY_CAP):
            assert arbiter.offer(nudge("GLOW", 0.5, "determined"), now) == "accepted"
            now += config.PER_USER_COOLDOWN_S
        assert arbiter.offer(nudge("GLOW", 0.5, "determined"), now) == "per_user_cap"

    def test_one_spammer_does_not_limit_everyone_else(self):
        arbiter = Arbiter()
        for _ in range(50):
            arbiter.offer(nudge("GLOW", 1.0, "spammer"), 0.0)
        assert arbiter.offer(nudge("GLOW", 0.5, "innocent"), 0.0) == "accepted"


class TestGlobalCooldowns:
    def test_profile_cooldown_is_the_thrash_guard(self):
        arbiter = Arbiter()
        for i in range(2):
            arbiter.offer(profile_action(SECOND, "a%d" % i), 0.0)
        first, _ = arbiter.resolve(config.VOTE_WINDOW_S)
        assert len(first) == 1

        for i in range(2):
            arbiter.offer(profile_action(FIRST, "b%d" % i), config.VOTE_WINDOW_S + 1)
        second, _ = arbiter.resolve(config.VOTE_WINDOW_S + 2)
        assert second == [], "a profile change 2s after the last one is thrash"
        assert arbiter.counters.get("cooldown_PROFILE") == 1

        # The cooldown runs from the EMIT at t=VOTE_WINDOW_S, not from the
        # suppressed attempt, so the next legal change is a full minute later.
        legal = config.VOTE_WINDOW_S + config.ACTION_COOLDOWN_S["PROFILE"]
        for i in range(2):
            arbiter.offer(profile_action(FIRST, "c%d" % i), legal)
        third, _ = arbiter.resolve(legal + 1)
        assert [d.target for d in third] == [FIRST]

    def test_a_suppressed_window_does_not_consume_the_next_ones_budget(self):
        """Cooldowns are stamped for what is EMITTED, not what is decided."""
        arbiter = Arbiter()
        arbiter.enabled = False
        for i in range(2):
            arbiter.offer(profile_action(SECOND, "a%d" % i), 0.0)
        assert arbiter.resolve(config.VOTE_WINDOW_S)[0] == []

        arbiter.enabled = True
        for i in range(2):
            arbiter.offer(profile_action(SECOND, "b%d" % i), config.VOTE_WINDOW_S + 1)
        decisions, _ = arbiter.resolve(config.VOTE_WINDOW_S + 2)
        assert len(decisions) == 1, "the suppressed window burned no cooldown"


class TestPhotosensitivityCeiling:
    """The one section of the design that is not negotiable by anyone.

    Not by the audience, not by a vote, not by the intensity dial, and not by a
    compromised bridge -- ``audience_control.py`` enforces the same numbers
    again on the other side of the wire.
    """

    def test_strobe_duration_is_the_ceiling_regardless_of_what_was_asked(self):
        arbiter = Arbiter()
        greedy = oneshot("STROBE_BURST", "a")
        greedy.duration = 600.0
        arbiter.offer(greedy, 0.0)
        decisions = arbiter.take_oneshots(0.0)
        assert decisions[0].duration == config.STROBE_MAX_S == 1.5

    def test_strobe_spacing_cannot_be_shortened_by_volume(self):
        arbiter = Arbiter()
        arbiter.offer(oneshot("STROBE_BURST", "first"), 0.0)
        assert len(arbiter.take_oneshots(0.0)) == 1
        emitted = 0
        attempts = 0
        now = 0.1
        while now < config.STROBE_MIN_INTERVAL_S:
            attempts += 1
            arbiter.offer(oneshot("STROBE_BURST", "u%d" % attempts), now)
            emitted += len(arbiter.take_oneshots(now))
            now += 0.1
        assert attempts > 100, "the room really did keep asking"
        assert emitted == 0, "no amount of asking shortens the 20 s spacing"

    def test_strobe_is_allowed_again_only_after_the_full_interval(self):
        arbiter = Arbiter()
        arbiter.offer(oneshot("STROBE_BURST", "a"), 0.0)
        arbiter.take_oneshots(0.0)
        later = config.STROBE_MIN_INTERVAL_S
        arbiter.offer(oneshot("STROBE_BURST", "b"), later)
        assert len(arbiter.take_oneshots(later)) == 1

    def test_the_intensity_dial_cannot_raise_the_ceiling(self):
        arbiter = Arbiter()
        arbiter.gain = 1.0
        arbiter.offer(oneshot("STROBE_BURST", "a"), 0.0)
        assert arbiter.take_oneshots(0.0)[0].duration == config.STROBE_MAX_S

    @pytest.mark.parametrize("target", list(config.ONESHOT_LIMITS))
    def test_every_oneshot_has_a_duration_and_spacing_limit(self, target):
        max_s, interval = config.ONESHOT_LIMITS[target]
        assert 0 < max_s <= 2.0
        assert interval >= 6.0

    def test_an_unlisted_oneshot_is_refused_rather_than_defaulted(self):
        """Adding a one-shot without a ceiling entry must fail closed."""
        arbiter = Arbiter()
        allowed, duration = arbiter.ceiling_for("MEGA_STROBE", 0.0)
        assert allowed is False and duration == 0.0

    def test_the_flash_rate_is_below_the_wcag_threshold(self):
        """WCAG 2.3.1's general flash threshold is more than three per second."""
        assert config.STROBE_HZ_CAP <= 3.0
        assert gp.STROBE_HZ_CAP == config.STROBE_HZ_CAP

    @pytest.mark.parametrize("name", [
        "STROBE_HZ_CAP", "STROBE_MAX_S", "STROBE_MIN_INTERVAL_S",
        "WHITEOUT_MAX_S", "ONESHOT_LIMITS",
    ])
    def test_the_ceiling_is_never_assigned_outside_its_declaration(self, name):
        """No code path writes these at runtime, in either process.

        A constant that something can re-assign is a tunable, and the whole
        claim of this section is that these are not tunables. Reads are fine;
        an assignment or an item-assignment is not.
        """
        files = list((REPO / "python" / "chat_bridge").glob("*.py"))
        files.append(REPO / "touchdesigner" / "scripts" / "audience_control.py")
        files.append(REPO / "touchdesigner" / "scripts" / "dj_graphics_profiles.py")
        pattern = re.compile(
            r"^\s*(?:config\.|gp\.|aud\.)?%s\s*(?:\[[^\]]*\])?\s*"
            r"(?::[^=]+)?=(?!=)" % name)
        writes = []
        for path in files:
            for line in path.read_text(encoding="utf-8").splitlines():
                if pattern.match(line):
                    writes.append("%s: %s" % (path.name, line.strip()))
        assert len(writes) <= 2, "%s is assigned more than declared: %s" % (
            name, writes)
        assert all(w.startswith(("config.py", "audience_control.py",
                                 "dj_graphics_profiles.py")) for w in writes), writes


class TestOperatorOverride:
    def test_his_action_wins_and_keeps_winning(self):
        """The failure everyone hits first: a stale vote flips his choice back."""
        arbiter = Arbiter()
        for i in range(5):
            arbiter.offer(profile_action(SECOND, "u%d" % i), 0.0)
        arbiter.arm_lockout(1.0)                       # Thomas taps a button
        decisions, tally = arbiter.resolve(config.VOTE_WINDOW_S)
        assert decisions == [], "the vote was in flight; his choice stands"
        assert tally["PROFILE:%s" % SECOND] == 5, "and it is still logged"

    def test_the_lockout_self_clears(self):
        """A timer, not a mode. He never has to re-enable anything."""
        arbiter = Arbiter()
        arbiter.arm_lockout(0.0)
        assert arbiter.locked_out(config.OPERATOR_LOCKOUT_S - 0.1)
        assert not arbiter.locked_out(config.OPERATOR_LOCKOUT_S)

    def test_a_second_tap_extends_rather_than_shortens(self):
        arbiter = Arbiter()
        arbiter.arm_lockout(0.0)
        arbiter.arm_lockout(30.0)
        assert arbiter.locked_out(30.0 + config.OPERATOR_LOCKOUT_S - 0.1)

    def test_panic_clears_the_window_and_holds_the_room(self):
        arbiter = Arbiter()
        for i in range(5):
            arbiter.offer(profile_action(SECOND, "u%d" % i), 0.0)
        arbiter.offer(oneshot("WHITEOUT", "someone"), 0.0)
        arbiter.panic(1.0)
        assert arbiter.take_oneshots(1.0) == [], "in-flight one-shots are dropped"
        decisions, tally = arbiter.resolve(config.VOTE_WINDOW_S)
        assert decisions == [] and tally == {}, "pending votes are discarded"
        assert arbiter.locked_out(1.0 + config.PANIC_LOCKOUT_S - 1)
        assert not arbiter.locked_out(1.0 + config.PANIC_LOCKOUT_S)

    def test_panic_holds_longer_than_an_ordinary_override(self):
        assert config.PANIC_LOCKOUT_S > config.OPERATOR_LOCKOUT_S


class TestKillSwitchAndDial:
    def test_disabled_suppresses_everything(self):
        arbiter = Arbiter()
        arbiter.enabled = False
        for i in range(5):
            arbiter.offer(profile_action(SECOND, "u%d" % i), 0.0)
        arbiter.offer(oneshot("COLOR_POP", "u", colour="ACID"), 0.0)
        assert arbiter.take_oneshots(0.0) == []
        assert arbiter.resolve(config.VOTE_WINDOW_S)[0] == []

    def test_disabled_still_tallies_so_the_log_is_not_silent(self):
        arbiter = Arbiter()
        arbiter.enabled = False
        for i in range(3):
            arbiter.offer(profile_action(SECOND, "u%d" % i), 0.0)
        _, tally = arbiter.resolve(config.VOTE_WINDOW_S)
        assert tally["PROFILE:%s" % SECOND] == 3

    def test_gain_scales_scalars(self):
        arbiter = Arbiter()
        arbiter.gain = 0.3
        arbiter.offer(nudge("GLOW", 1.0, "a"), 0.0)
        decisions, _ = arbiter.resolve(config.VOTE_WINDOW_S)
        assert decisions[0].amount == pytest.approx(0.3)

    def test_gain_of_zero_means_they_can_watch(self):
        arbiter = Arbiter()
        arbiter.gain = 0.0
        arbiter.offer(nudge("GLOW", 1.0, "a"), 0.0)
        assert arbiter.resolve(config.VOTE_WINDOW_S)[0] == []

    @pytest.mark.parametrize("gain", [-5.0, 1.5, 99.0])
    def test_an_out_of_range_gain_cannot_amplify(self, gain):
        arbiter = Arbiter()
        arbiter.gain = gain
        arbiter.offer(nudge("GLOW", 1.0, "a"), 0.0)
        decisions, _ = arbiter.resolve(config.VOTE_WINDOW_S)
        for decision in decisions:
            assert abs(decision.amount) <= config.NUDGE_MAX

    def test_profile_lock_keeps_nudges_and_oneshots(self):
        """The natural setting for a peak-time moment he wants to own."""
        arbiter = Arbiter()
        arbiter.lock_profile = True
        assert arbiter.offer(profile_action(SECOND, "a"), 0.0) == "profile_locked"
        assert arbiter.offer(nudge("GLOW", 0.5, "b"), 0.0) == "accepted"
        assert arbiter.offer(oneshot("COLOR_POP", "c", colour="ACID"), 0.0) == "accepted"
        decisions = arbiter.take_oneshots(0.0)
        decisions += arbiter.resolve(config.VOTE_WINDOW_S)[0]
        assert {d.verb for d in decisions} == {"NUDGE", "ONESHOT"}


class TestDegradation:
    def test_nothing_asked_for_means_nothing_emitted(self):
        arbiter = Arbiter()
        assert arbiter.resolve(1e6) == ([], {})
        assert arbiter.take_oneshots(1e6) == []

    def test_an_outage_does_not_stampede_at_recovery(self):
        """Batches are skipped, never queued. This asserts the consequence.

        Ten minutes of silence followed by a burst still produces one profile
        change, because the tally only ever describes the current window.
        """
        arbiter = Arbiter()
        for i in range(40):
            arbiter.offer(profile_action(SECOND, "u%d" % i), 600.0)
        decisions, _ = arbiter.resolve(600.0 + config.VOTE_WINDOW_S)
        assert len(decisions) == 1
