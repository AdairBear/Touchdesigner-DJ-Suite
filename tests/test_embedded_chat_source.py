"""Offline tests for the Embedded Chat reader and the multi-source merge.

Two things are being asserted here, and only one of them is about parsing.

The first is that the reader is RECEIVE-ONLY by construction. It is pointed at
a chat room that belongs to somebody else, on a night when Thomas is not the
one who can fix it, so the test looks at the socket's emit log and asserts that
the only thing that ever leaves this process is ``join``.

The second is that the field mapping -- which is a best-effort guess, because
the provider's payload schema has never been read off a live room -- is loud
about every guess it has to make. A source that silently maps the wrong key
looks exactly like a quiet chat, which is the silent-failure shape the
fail-loud rule exists to prevent.

Run:  ./venv/bin/python -m pytest tests/test_embedded_chat_source.py -v
"""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent.parent
sys.path.insert(0, str(REPO / "python"))

from chat_bridge import config  # noqa: E402
from chat_bridge.model import ChatMessage  # noqa: E402
from chat_bridge.sources import (ChatSource, EmbeddedChatSource,  # noqa: E402
                                 MergeSource, QuotaExhausted,
                                 map_embedded_payload)


class FakeSocket:
    """A Socket.IO client that records instead of connecting.

    Attributes:
        handlers: Event name -> callback, as registered by the source.
        emitted: Every ``(event, args)`` the source sent. The receive-only
            assertion reads this.
        connect_calls: Every ``(url, kwargs)`` passed to ``connect``.
        disconnected: Whether ``disconnect`` was called.
    """

    def __init__(self, fail_connect=None):
        self.handlers = {}
        self.emitted = []
        self.connect_calls = []
        self.disconnected = False
        self._fail_connect = fail_connect

    def on(self, event, handler=None):
        self.handlers[event] = handler
        return handler

    def connect(self, url, **kwargs):
        if self._fail_connect is not None:
            raise self._fail_connect
        self.connect_calls.append((url, kwargs))
        handler = self.handlers.get("connect")
        if handler:
            handler()

    def emit(self, event, *args):
        self.emitted.append((event, args))

    def disconnect(self):
        self.disconnected = True

    # --- test driver ---------------------------------------------------------

    def deliver(self, *payload):
        """Fire the source's ``message`` handler.

        Args:
            *payload: Positional args as the provider would emit them.
        """
        self.handlers["message"](*payload)


def opened_source(**kwargs):
    """Build and open an EmbeddedChatSource wired to a FakeSocket.

    Args:
        **kwargs: Passed through to the source.

    Returns:
        ``(source, socket, warnings)``.
    """
    socket = FakeSocket()
    warnings = []
    source = EmbeddedChatSource(client_factory=lambda: socket,
                                warn_fn=warnings.append, **kwargs)
    source.open()
    return source, socket, warnings


# ---------------------------------------------------------------------------
# Receive-only: the property that matters most
# ---------------------------------------------------------------------------
class TestReceiveOnly:
    def test_the_only_event_ever_emitted_is_join(self):
        source, socket, _ = opened_source()
        socket.deliver({"message": "more strobe", "user": "raverkid"})
        source.poll()
        source.close()
        assert [event for event, _ in socket.emitted] == ["join"]

    def test_join_carries_the_room_id_and_nothing_else(self):
        _, socket, _ = opened_source(room="292041")
        assert socket.emitted == [("join", ("292041",))]

    def test_no_credential_is_ever_sent(self):
        _, socket, _ = opened_source()
        blob = repr(socket.emitted) + repr(socket.connect_calls)
        for secret in ("token", "auth", "password", "cookie", "login",
                       "session", "api_key"):
            assert secret not in blob.lower()

    def test_the_source_exposes_no_posting_method(self):
        """A reader that cannot speak cannot be talked into speaking."""
        for forbidden in ("send", "post", "say", "login", "authenticate",
                          "reply"):
            assert not hasattr(EmbeddedChatSource, forbidden)

    def test_rejoins_after_a_reconnect(self):
        """python-socketio re-fires ``connect``; the room must be re-joined."""
        _, socket, _ = opened_source()
        socket.handlers["connect"]()
        assert [event for event, _ in socket.emitted] == ["join", "join"]


# ---------------------------------------------------------------------------
# Field mapping -- best effort, and loud about it
# ---------------------------------------------------------------------------
class TestFieldMapping:
    @pytest.mark.parametrize("payload", [
        {"message": "more strobe", "user": "raverkid"},
        {"text": "more strobe", "name": "raverkid"},
        {"body": "more strobe", "nick": "raverkid"},
        {"content": "more strobe", "username": "raverkid"},
        {"msg": "more strobe", "author": "raverkid"},
    ])
    def test_each_candidate_schema_maps(self, payload):
        message = map_embedded_payload(payload)
        assert message.text == "more strobe"
        assert message.author_name == "raverkid"

    def test_nested_author_object(self):
        message = map_embedded_payload(
            {"message": "acid please", "user": {"name": "raverkid", "id": 77}})
        assert message.author_name == "raverkid"
        assert message.author_id == "77"

    def test_a_json_string_payload_is_parsed(self):
        message = map_embedded_payload('{"message": "hi", "user": "kid"}')
        assert message.text == "hi" and message.author_name == "kid"

    def test_a_bare_string_payload_becomes_text_with_a_warning(self):
        warnings = []
        message = map_embedded_payload("just text", warn_fn=warnings.append)
        assert message.text == "just text"
        assert any("author" in w for w in warnings)

    def test_a_payload_with_no_text_is_dropped_loudly(self):
        warnings = []
        assert map_embedded_payload({"type": "presence", "user": "kid"},
                                    warn_fn=warnings.append) is None
        assert any("no text field" in w for w in warnings)

    def test_a_non_object_payload_is_dropped_loudly(self):
        warnings = []
        assert map_embedded_payload(42, warn_fn=warnings.append) is None
        assert any("not an object" in w for w in warnings)

    def test_a_fallback_text_key_is_reported(self):
        warnings = []
        map_embedded_payload({"content": "hi", "user": "kid"},
                             warn_fn=warnings.append)
        assert any("fallback key" in w for w in warnings)

    def test_the_expected_keys_do_not_warn(self):
        warnings = []
        map_embedded_payload({"message": "hi", "user": {"name": "kid", "id": 3}},
                             warn_fn=warnings.append)
        assert warnings == []

    def test_a_top_level_id_is_not_mistaken_for_the_author(self):
        """Otherwise every line gets a fresh identity and cooldowns stop working."""
        message = map_embedded_payload({"id": "msg-1", "message": "hi",
                                        "name": "kid"})
        assert message.msg_id == "msg-1"
        assert message.author_id == "kid"

    def test_missing_ids_still_produce_distinct_messages(self):
        first = map_embedded_payload({"message": "hi", "name": "kid"}, seq=1)
        second = map_embedded_payload({"message": "hi", "name": "kid"}, seq=2)
        assert first.msg_id != second.msg_id

    def test_the_platform_timestamp_is_not_used_as_the_clock(self):
        """Every limiter compares one monotonic clock; a platform ts is data."""
        message = map_embedded_payload({"message": "hi", "name": "kid",
                                        "time": 0})
        assert message.ts > 0

    def test_hostile_name_is_sanitized_by_the_model_not_the_source(self):
        message = map_embedded_payload(
            {"message": "hi", "name": "‮DJ<script>"})
        assert message.safe_name == "DJscript"


# ---------------------------------------------------------------------------
# The push-into-a-buffer / pull-from-poll contract
# ---------------------------------------------------------------------------
class TestSourceContract:
    def test_it_is_a_chatsource(self):
        assert issubclass(EmbeddedChatSource, ChatSource)

    def test_delivered_messages_arrive_on_poll(self):
        source, socket, _ = opened_source()
        socket.deliver({"message": "more glow", "user": "kid"})
        socket.deliver({"message": "strobe", "user": "other"})
        out = source.poll()
        assert [m.text for m in out] == ["more glow", "strobe"]
        assert all(m.source == "embedded-chat" for m in out)

    def test_poll_drains(self):
        source, socket, _ = opened_source()
        socket.deliver({"message": "hi", "user": "kid"})
        assert len(source.poll()) == 1
        assert source.poll() == []

    def test_unmappable_events_never_reach_the_buffer(self):
        source, socket, _ = opened_source()
        socket.deliver({"type": "user_joined", "user": "kid"})
        assert source.poll() == []
        assert source.received == 1 and source.mapped == 0

    def test_the_buffer_is_bounded(self):
        source, socket, warnings = opened_source()
        for i in range(config.EMBEDDED_CHAT_BUFFER_MAX + 25):
            socket.deliver({"message": "line %d" % i, "user": "kid"})
        assert len(source.poll()) == config.EMBEDDED_CHAT_BUFFER_MAX
        assert source.dropped_overflow == 25
        assert any("buffer full" in w for w in warnings)

    def test_a_failed_connect_raises_so_the_bridge_can_alert(self):
        source = EmbeddedChatSource(
            client_factory=lambda: FakeSocket(fail_connect=OSError("refused")))
        with pytest.raises(OSError):
            source.open()

    def test_close_disconnects(self):
        source, socket, _ = opened_source()
        source.close()
        assert socket.disconnected

    def test_close_is_idempotent(self):
        source, _, _ = opened_source()
        source.close()
        source.close()

    def test_a_warning_is_reported_once_not_once_per_line(self):
        source, socket, warnings = opened_source()
        for i in range(20):
            socket.deliver({"content": "line %d" % i, "name": "kid"})
        assert len([w for w in warnings if "fallback key" in w]) == 1

    def test_the_raw_sink_sees_payloads_and_does_not_gate_them(self):
        captured = []
        socket = FakeSocket()
        source = EmbeddedChatSource(client_factory=lambda: socket,
                                    raw_sink=captured.append)
        source.open()
        socket.deliver({"message": "hi", "user": "kid"})
        assert captured == [{"message": "hi", "user": "kid"}]

    def test_a_raw_sink_that_explodes_does_not_lose_the_message(self):
        def boom(_):
            raise IOError("disk full")

        socket = FakeSocket()
        warnings = []
        source = EmbeddedChatSource(client_factory=lambda: socket,
                                    raw_sink=boom, warn_fn=warnings.append)
        source.open()
        socket.deliver({"message": "hi", "user": "kid"})
        assert len(source.poll()) == 1
        assert any("raw capture failed" in w for w in warnings)


# ---------------------------------------------------------------------------
# MergeSource
# ---------------------------------------------------------------------------
class StubSource(ChatSource):
    """A ChatSource that yields scripted batches.

    Args:
        name: Source name.
        batches: One list of ``(author, text)`` per poll.
        open_error: Raised from ``open``.
        poll_error: Raised from every ``poll``.
        delay: What ``next_poll_delay`` reports.
    """

    def __init__(self, name, batches=(), open_error=None, poll_error=None,
                 delay=1.0):
        self.name = name
        self._batches = list(batches)
        self._open_error = open_error
        self._poll_error = poll_error
        self._delay = delay
        self.opened = False
        self.closed = False
        self.polls = 0

    def open(self):
        self.opened = True
        if self._open_error:
            raise self._open_error

    def poll(self):
        self.polls += 1
        if self._poll_error:
            raise self._poll_error
        if not self._batches:
            return []
        return [ChatMessage(msg_id="m%d" % i, author_id=author,
                            author_name=author, text=text, ts=0.0,
                            source=self.name)
                for i, (author, text) in enumerate(self._batches.pop(0))]

    def next_poll_delay(self):
        return self._delay

    def close(self):
        self.closed = True


class TestMergeSource:
    def test_it_is_a_chatsource_so_chatbridge_needs_no_change(self):
        assert issubclass(MergeSource, ChatSource)

    def test_both_children_are_opened(self):
        a, b = StubSource("a"), StubSource("b")
        MergeSource([a, b]).open()
        assert a.opened and b.opened

    def test_messages_from_both_sources_interleave_in_one_poll(self):
        merge = MergeSource([StubSource("embedded-chat", [[("kid", "glow")]]),
                             StubSource("youtube", [[("chan", "strobe")]])])
        merge.open()
        out = merge.poll()
        assert [m.text for m in out] == ["glow", "strobe"]

    def test_every_message_is_tagged_with_its_source(self):
        merge = MergeSource([StubSource("embedded-chat", [[("kid", "glow")]]),
                             StubSource("youtube", [[("chan", "strobe")]])])
        merge.open()
        assert [m.source for m in merge.poll()] == ["embedded-chat", "youtube"]

    def test_ids_are_namespaced_so_two_platforms_cannot_collide(self):
        """Same raw ids on both sides must not dedupe each other away."""
        merge = MergeSource([StubSource("embedded-chat", [[("kid", "glow")]]),
                             StubSource("youtube", [[("kid", "strobe")]])])
        merge.open()
        out = merge.poll()
        assert out[0].msg_id != out[1].msg_id
        assert out[0].author_id != out[1].author_id
        assert out[0].author_id.startswith("embedded-chat:")

    def test_a_child_that_raises_does_not_stop_the_other(self):
        alerts = []
        merge = MergeSource([StubSource("dead", poll_error=OSError("gone")),
                             StubSource("embedded-chat", [[("kid", "glow")]])],
                            alert_fn=alerts.append)
        merge.open()
        assert [m.text for m in merge.poll()] == ["glow"]
        assert any("poll failed" in a for a in alerts)

    def test_a_child_that_exhausts_quota_is_retired_not_fatal(self):
        """On a single-source bridge QuotaExhausted stops the run. Not here."""
        alerts = []
        dead = StubSource("youtube", poll_error=QuotaExhausted("spent"))
        live = StubSource("embedded-chat", [[("kid", "glow")], [("kid", "hi")]])
        merge = MergeSource([dead, live], alert_fn=alerts.append)
        merge.open()
        assert [m.text for m in merge.poll()] == ["glow"]
        assert [m.text for m in merge.poll()] == ["hi"]
        assert dead.polls == 1, "a retired source must not be polled again"
        assert any("retired" in a for a in alerts)

    def test_a_child_that_fails_to_open_is_dropped_with_an_alert(self):
        alerts = []
        merge = MergeSource([StubSource("youtube", open_error=OSError("no")),
                             StubSource("embedded-chat", [[("kid", "glow")]])],
                            alert_fn=alerts.append)
        merge.open()
        assert [m.text for m in merge.poll()] == ["glow"]
        assert any("failed to open" in a for a in alerts)

    def test_every_child_failing_to_open_is_fatal(self):
        merge = MergeSource([StubSource("a", open_error=OSError("no")),
                             StubSource("b", open_error=OSError("no"))])
        with pytest.raises(RuntimeError):
            merge.open()

    def test_cadence_is_the_most_impatient_live_child(self):
        merge = MergeSource([StubSource("a", delay=5.0),
                             StubSource("b", delay=1.0)])
        assert merge.next_poll_delay() == 1.0

    def test_close_closes_every_child(self):
        a, b = StubSource("a"), StubSource("b")
        merge = MergeSource([a, b])
        merge.close()
        assert a.closed and b.closed

    def test_an_empty_merge_is_refused(self):
        with pytest.raises(ValueError):
            MergeSource([])


# ---------------------------------------------------------------------------
# The bridge is unchanged: a merged source drives it exactly like a single one
# ---------------------------------------------------------------------------
class TestBridgeIsUntouched:
    def test_chatbridge_still_takes_exactly_one_source(self):
        import inspect

        from chat_bridge.bridge import ChatBridge

        params = inspect.signature(ChatBridge.__init__).parameters
        assert "source" in params and "sources" not in params

    def test_a_merged_source_runs_the_normal_loop(self, tmp_path):
        from chat_bridge.bridge import ChatBridge, NdjsonLog

        merge = MergeSource([StubSource("embedded-chat", [[("kid", "hello")]]),
                             StubSource("youtube", [[("chan", "hi")]])])
        bridge = ChatBridge(source=merge, log=NdjsonLog(str(tmp_path / "l.ndjson")),
                            interpreter=_null_interpreter(),
                            moderator=_null_moderator(),
                            emitter=_null_emitter())
        merge.open()
        assert bridge.ingest(0.0) == 2


# ---------------------------------------------------------------------------
# --capture-raw: the tool that turns the guessed schema into a known one
# ---------------------------------------------------------------------------
class TestCaptureRaw:
    def _run(self, tmp_path, payloads):
        """Drive capture_raw over a fake socket.

        Args:
            tmp_path: pytest tmp dir.
            payloads: Payloads to deliver, one per loop iteration.

        Returns:
            ``(exit_code, file_text)``.
        """
        from chat_bridge.__main__ import capture_raw

        socket = FakeSocket()
        source = EmbeddedChatSource(client_factory=lambda: socket)
        pending = list(payloads)

        def sleep_fn(_seconds):
            if not pending:
                raise KeyboardInterrupt
            socket.deliver(pending.pop(0))

        path = tmp_path / "raw.json"
        code = capture_raw("292041", str(path), source=source,
                           sleep_fn=sleep_fn)
        return code, path.read_text(encoding="utf-8")

    def test_payloads_are_written_as_readable_json(self, tmp_path):
        code, text = self._run(tmp_path, [{"message": "hi", "user": "kid"}])
        assert code == 0
        assert '"message": "hi"' in text and '"user": "kid"' in text

    def test_it_captures_payloads_it_cannot_map(self, tmp_path):
        """The unmappable ones are the whole point -- they name the real schema."""
        _, text = self._run(tmp_path, [{"mystery_field": "hi", "who": "kid"}])
        assert "mystery_field" in text

    def test_capture_mode_never_builds_a_pipeline(self, tmp_path, monkeypatch):
        """No moderation, no interpreter, no emitter: the gates are not in it."""
        import chat_bridge.bridge as bridge_mod

        def explode(*_args, **_kwargs):
            raise AssertionError("capture-raw must not construct a ChatBridge")

        monkeypatch.setattr(bridge_mod.ChatBridge, "__init__", explode)
        code, _ = self._run(tmp_path, [{"message": "hi", "user": "kid"}])
        assert code == 0

    def test_a_connect_failure_is_reported_not_raised(self, tmp_path):
        from chat_bridge.__main__ import capture_raw

        source = EmbeddedChatSource(
            client_factory=lambda: FakeSocket(fail_connect=OSError("refused")))
        assert capture_raw("292041", str(tmp_path / "raw.json"),
                           source=source, sleep_fn=lambda _s: None) == 1

    def test_the_flag_short_circuits_before_the_openai_key_check(self, monkeypatch):
        """Capture needs no key, because nothing downstream of it exists."""
        import chat_bridge.__main__ as cli

        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setattr(cli, "capture_raw",
                            lambda room, path, duration_s=None: 0)
        assert cli.main(["--source", "embedded", "--capture-raw", "x.json"]) == 0

    def test_the_room_defaults_to_the_kniteforce_channel(self):
        from chat_bridge.__main__ import parse_args

        assert parse_args([]).room == config.EMBEDDED_CHAT_ROOM == "292041"


def _null_interpreter():
    """An interpreter that classifies nothing.

    Returns:
        An object with the Interpreter surface the bridge touches.
    """
    class Null:
        calls = 0
        failures = 0

        def classify(self, messages):
            return [], []

    return Null()


def _null_moderator():
    """A moderator that passes everything, without a network call.

    Returns:
        An object with the Moderator surface the bridge touches.
    """
    class Null:
        total_errored = 0

        def check_batch(self, messages):
            return list(messages), []

    return Null()


def _null_emitter():
    """An emitter that swallows packets.

    Returns:
        An object with the Emitter surface the bridge touches.
    """
    class Null:
        host = "127.0.0.1"
        port = 0
        last_error = None

        def send(self, decision):
            return True

    return Null()
