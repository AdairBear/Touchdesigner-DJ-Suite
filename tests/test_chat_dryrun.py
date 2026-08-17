"""Tests for the offline dry-run harness (chat_bridge/dryrun.py).

The harness exists to be *believed* -- its report is what a human reads before
deciding HIVE is safe to point at a live stream. So the things asserted here are
mostly about honesty: that it runs the real gates rather than reimplementing
them, that it cannot spend money by accident, and that its corpus stays loadable.
"""

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "touchdesigner" / "scripts"))
sys.path.insert(0, str(REPO / "python"))

from chat_bridge import config, dryrun  # noqa: E402
from chat_bridge.model import ChatMessage  # noqa: E402


class TestCorpus:
    def test_the_shipped_corpus_loads(self):
        records = dryrun.load_corpus(dryrun.DEFAULT_CORPUS)
        assert len(records) >= 30

    def test_every_record_carries_an_expectation(self):
        """An unlabelled line is a line nobody reviews."""
        for record in dryrun.load_corpus(dryrun.DEFAULT_CORPUS):
            assert record.get("expect"), record["msg_id"]
            assert record.get("why"), record["msg_id"]

    def test_expectations_use_the_documented_vocabulary(self):
        legal = {"NONE", "BLOCKED"}
        for record in dryrun.load_corpus(dryrun.DEFAULT_CORPUS):
            expect = record["expect"]
            if expect in legal:
                continue
            verb, _, target = expect.partition(":")
            assert verb in config.VERBS, expect
            assert target, expect

    def test_a_malformed_corpus_line_names_itself(self, tmp_path):
        """Silently skipping a bad line would silently drop a test case."""
        path = tmp_path / "bad.jsonl"
        path.write_text('{"msg_id": "a", "author_id": "a", '
                        '"author_name": "a", "text": "hi"}\nnot json\n',
                        encoding="utf-8")
        with pytest.raises(ValueError, match=":2"):
            dryrun.load_corpus(str(path))

    def test_a_record_missing_a_field_names_the_field(self, tmp_path):
        path = tmp_path / "short.jsonl"
        path.write_text('{"msg_id": "a", "author_id": "a"}\n', encoding="utf-8")
        with pytest.raises(ValueError, match="author_name"):
            dryrun.load_corpus(str(path))


class TestOfflineEngine:
    def test_it_emits_the_live_response_schema_shape(self):
        """The stand-in must be substitutable for the model, not merely similar."""
        batch = [ChatMessage("m1", "u1", "u1", "more glow", 0.0)]
        payload = dryrun.offline_classify(batch)
        assert set(payload) == {"actions"}
        for action in payload["actions"]:
            assert set(action) == {"i", "verb", "target", "amount", "colour",
                                   "confidence"}
            assert action["verb"] in config.VERBS

    def test_its_output_survives_the_real_validator(self):
        from chat_bridge import validator

        batch = [ChatMessage("m1", "u1", "u1", "more glow", 0.0)]
        actions, _ = validator.validate_response(
            dryrun.offline_classify(batch), batch)
        assert [(a.verb, a.target) for a in actions] == [("NUDGE", "GLOW")]

    def test_the_completion_shim_round_trips_render_batch(self):
        """Indices come back through the rendered block, not a closure.

        If render_batch's numbering ever stopped round-tripping, the harness
        would misattribute exactly the way a confused model would -- which is
        the failure worth catching, so it is exercised rather than bypassed.
        """
        from chat_bridge.interpreter import render_batch

        batch = [ChatMessage("m1", "u1", "u1", "hi there", 0.0),
                 ChatMessage("m2", "u2", "u2", "more zoom", 0.0)]
        raw = dryrun.offline_completion(
            system="", user=render_batch(batch), schema={}, model="x",
            timeout=1.0)
        payload = json.loads(raw)
        assert payload["actions"][1]["i"] == 1
        assert payload["actions"][1]["target"] == "ZOOM"

    def test_a_nudge_never_lands_on_zero(self):
        """validator drops a zero nudge, so a zero here is a silent no-op."""
        for text in ("more glow", "less glow", "glow", "way more glow"):
            batch = [ChatMessage("m", "u", "u", text, 0.0)]
            for action in dryrun.offline_classify(batch)["actions"]:
                if action["verb"] == "NUDGE":
                    assert action["amount"] != 0.0, text

    def test_an_rgb_triple_never_becomes_a_colour(self):
        """The audience cannot author a colour outside the neon anchors."""
        assert dryrun._colour_in("color pop in #ff00ff") is None
        assert dryrun._colour_in("colour pop rgb(1,2,3)") is None

    def test_it_cannot_invent_a_target_outside_the_enums(self):
        legal = set(config.NUDGE_TARGETS) | set(config.ONESHOT_TARGETS) | {"NONE"}
        from chat_bridge import validator

        legal |= set(validator.valid_profile_targets())
        for record in dryrun.load_corpus(dryrun.DEFAULT_CORPUS):
            batch = [ChatMessage("m", "u", "u", record["text"], 0.0)]
            for action in dryrun.offline_classify(batch)["actions"]:
                assert action["target"] in legal, record["msg_id"]


class TestTheRunIsTheRealPipeline:
    """The harness must not become a second, kinder implementation."""

    def test_structural_moderation_really_runs(self):
        """The BLOCKED lines are blocked by the production screen, not a stub."""
        report = dryrun.run(dryrun.load_corpus(dryrun.DEFAULT_CORPUS))
        blocked = [r for r in report["engine_rows"]
                   if r["stopped_at"] == "moderation"]
        assert blocked, "no line exercised the structural screen"
        for row in blocked:
            assert row["expect"] == "BLOCKED"

    def test_the_photosensitivity_ceiling_is_applied_not_requested(self):
        """A 60-second strobe request must come out at the ceiling.

        This is the one the whole safety argument rests on: the model does not
        get to choose a duration at all.
        """
        batch = [ChatMessage("m", "u", "u", "strobe burst for 60 seconds", 0.0)]
        from chat_bridge import validator

        actions, _ = validator.validate_response(
            {"actions": [{"i": 0, "verb": "ONESHOT", "target": "STROBE_BURST",
                          "amount": 0.0, "colour": None, "confidence": 0.99,
                          "duration": 60.0}]}, batch)
        assert actions
        assert actions[0].duration == config.STROBE_MAX_S

    def test_the_report_is_deterministic(self):
        """A synthetic clock, so the output is diffable between runs."""
        records = dryrun.load_corpus(dryrun.DEFAULT_CORPUS)
        first = dryrun.run(records)
        second = dryrun.run(records)
        assert first["engine_rows"] == second["engine_rows"]
        assert first["decisions"] == second["decisions"]

    def test_no_row_is_left_unreached(self):
        """`unreached` means a gate dropped a message without saying so."""
        report = dryrun.run(dryrun.load_corpus(dryrun.DEFAULT_CORPUS))
        stuck = [r["msg_id"] for r in report["engine_rows"]
                 if r["stopped_at"] == "unreached"]
        assert not stuck, "rows fell through every stage: %s" % stuck

    def test_arbitration_is_reported_separately_from_classification(self):
        """Quorum holding a vote is the system working, not a misclassification."""
        report = dryrun.run(dryrun.load_corpus(dryrun.DEFAULT_CORPUS))
        held = [r for r in report["engine_rows"] if r["arbiter"] not in ("", "accepted")]
        assert held, "nothing exercised the arbiter's refusals"
        for row in held:
            # It still classified; only the arbiter declined to act on it.
            assert row["verb"], row["msg_id"]

    def test_the_report_renders(self):
        text = dryrun.format_report(
            dryrun.run(dryrun.load_corpus(dryrun.DEFAULT_CORPUS)))
        assert "AGREEMENT WITH CORPUS" in text
        assert "DECISIONS ACTUALLY EMITTED" in text


class TestItCannotSpendMoneyByAccident:
    """The whole point of a dry run is that it is dry."""

    def test_the_default_engine_is_offline(self):
        assert dryrun.parse_args([]).engine == "offline"

    def test_openai_without_approval_is_refused(self):
        args = dryrun.parse_args(["--engine", "openai"])
        with pytest.raises(SystemExit, match="paid"):
            dryrun._openai_guard(args)

    def test_openai_without_a_key_is_refused(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        args = dryrun.parse_args(
            ["--engine", "openai", "--i-approve-paid-calls"])
        with pytest.raises(SystemExit, match="OPENAI_API_KEY"):
            dryrun._openai_guard(args)

    def test_no_environment_variable_can_grant_approval(self, monkeypatch):
        """Approval is a flag typed by a human, every time.

        A harness whose billing can be switched on by an exported variable is
        one nobody can safely leave in a repo or a cron job.
        """
        for name in ("CHAT_BRIDGE_APPROVE", "I_APPROVE_PAID_CALLS",
                     "OPENAI_API_KEY"):
            monkeypatch.setenv(name, "1")
        args = dryrun.parse_args(["--engine", "openai"])
        with pytest.raises(SystemExit, match="paid"):
            dryrun._openai_guard(args)

    def test_a_default_run_makes_no_network_call(self, monkeypatch):
        """Belt and braces: poison the socket and run the whole corpus."""
        import socket

        def forbidden(*args, **kwargs):
            raise AssertionError("the offline dry run attempted a network call")

        monkeypatch.setattr(socket, "socket", forbidden)
        monkeypatch.setattr(socket, "create_connection", forbidden)
        report = dryrun.run(dryrun.load_corpus(dryrun.DEFAULT_CORPUS))
        assert report["totals"]["actions_validated"] > 0
