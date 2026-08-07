"""Chat ingestion, behind one interface so the reader is swappable.

Six implementations of one seam:

``YouTubeAPISource``   official Data API v3. OAuth for Thomas's own channel, a
                       plain API key for anyone else's public stream. Honours
                       the ``pollingIntervalMillis`` the API returns, never a
                       hardcoded cadence, and hard-stops on a quota budget.
``ChatDownloaderSource`` the escape hatch. No auth, no quota, no Cloud project
                       -- valuable in exactly one scenario, which is a token
                       dying ten minutes before doors. Unofficial and it will
                       break without warning, so it is not the default.
``EmbeddedChatSource`` the Kniteforce Radio site's own chat widget, read
                       anonymously over Socket.IO. Receive-only, by
                       construction: it emits exactly one event, ``join``.
``MergeSource``        fans N sources into one, so the site chat and a YouTube
                       stream can drive the same show without ``ChatBridge``
                       knowing there is more than one reader.
``ReplaySource``       reads an NDJSON log back. This is what makes an offline
                       rehearsal of a real stream possible.
``ListSource``         a list of messages. Tests.

Every one of them produces the same :class:`~chat_bridge.model.ChatMessage` and
feeds the same four gates downstream. A source is a reader; it is not, and must
never become, a place where a safety decision is taken.

The quota arithmetic deserves a warning: Google's quota table does not document
the live-streaming endpoints at all, so the per-call cost is UNKNOWN. Watch the
Cloud Console graph during the first stream and set ``CHAT_BRIDGE_UNIT_COST``
to what you measure. The default of 1 is the likely value, not a verified one.
"""

from __future__ import annotations

import collections
import json
import threading
import time
from typing import (Any, Callable, Deque, Dict, Iterable, Iterator, List,
                    Optional, Sequence, Tuple)

from . import config
from .model import ChatMessage


class QuotaExhausted(RuntimeError):
    """Raised when the budgeted quota is spent. Loud on purpose."""


class ChatSource:
    """The seam. A source yields ChatMessages and knows when to be polled again."""

    name = "base"

    def open(self) -> None:
        """Connect, authenticate, and resolve the live chat id."""

    def poll(self) -> List[ChatMessage]:
        """Fetch whatever has arrived.

        Returns:
            Zero or more messages.
        """
        raise NotImplementedError

    def next_poll_delay(self) -> float:
        """Seconds to wait before polling again.

        Returns:
            The cadence the source wants, never below a floor.
        """
        return config.YT_MIN_POLL_S

    def close(self) -> None:
        """Release anything held."""


class ListSource(ChatSource):
    """Yields a fixed list once. For tests and dry runs.

    Args:
        messages: What to yield on the first poll.
    """

    name = "list"

    def __init__(self, messages: Iterable[ChatMessage]) -> None:
        self._messages = list(messages)
        self._done = False

    def poll(self) -> List[ChatMessage]:
        """Yield the list, once.

        Returns:
            The messages on the first call, then nothing.
        """
        if self._done:
            return []
        self._done = True
        return list(self._messages)


class ReplaySource(ChatSource):
    """Replays an NDJSON log written by a previous run.

    This is how a Phase-1 log becomes an offline rehearsal: the same pipeline,
    the same decisions, no stream, no quota, no keys except the interpreter's.

    Args:
        path: NDJSON file with one ``{"event": "message", ...}`` per line.
        realtime: True replays at the original spacing; False dumps it all at
            once, which is what a fast test wants.
    """

    name = "replay"

    def __init__(self, path: str, realtime: bool = False) -> None:
        self.path = path
        self.realtime = realtime
        self._rows: List[dict] = []
        self._i = 0
        self._t0 = 0.0

    def open(self) -> None:
        """Load the log into memory."""
        self._rows = []
        with open(self.path, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("event") == "message":
                    self._rows.append(row)
        self._t0 = time.monotonic()

    def poll(self) -> List[ChatMessage]:
        """Yield the next slice of the log.

        Returns:
            Messages whose recorded offset has elapsed, or all remaining rows
            when not replaying in real time.
        """
        out: List[ChatMessage] = []
        now = time.monotonic()
        while self._i < len(self._rows):
            row = self._rows[self._i]
            if self.realtime and row.get("offset", 0.0) > now - self._t0:
                break
            self._i += 1
            out.append(ChatMessage(
                msg_id=str(row.get("msg_id", self._i)),
                author_id=str(row.get("author_id", "")),
                author_name=str(row.get("author_name", "")),
                text=str(row.get("text", "")),
                ts=now,
                source="replay",
            ))
        return out

    def next_poll_delay(self) -> float:
        """Cadence for replay.

        Returns:
            A short tick in real time, immediate otherwise.
        """
        return 0.5 if self.realtime else 0.0


class YouTubeAPISource(ChatSource):
    """Official YouTube Data API v3 reader.

    Two auth paths, and which one applies depends on whose stream it is:

    * Thomas's own channel needs OAuth with scope ``youtube.readonly``, because
      ``liveBroadcasts.list(mine=True)`` is user-scoped. An API key cannot do
      it. **The consent screen must be set to "In Production" -- one left in
      "Testing" has its refresh tokens revoked by Google after exactly seven
      days, and it fails silently, at stream start.**
    * Anyone else's PUBLIC stream needs only an API key, via
      ``videos.list(part=liveStreamingDetails)``. No OAuth, no ownership, none
      of the seven-day problem.

    Args:
        video_id: A specific video. None means "whatever I am streaming now",
            which requires OAuth.
        credentials: A google-auth credentials object. None uses an API key.
        api_key: For the public-video path.
        alert_fn: Called on token-refresh failure. A dead token is otherwise
            indistinguishable from a quiet chat, which is exactly the
            silent-failure shape the fail-loud rule exists to prevent.
    """

    name = "youtube"

    def __init__(self, video_id: Optional[str] = None,
                 credentials: Any = None, api_key: Optional[str] = None,
                 alert_fn: Optional[Callable[[str], None]] = None,
                 build_fn: Optional[Callable[..., Any]] = None) -> None:
        self.video_id = video_id
        self.credentials = credentials
        self.api_key = api_key
        self._alert = alert_fn or (lambda msg: None)
        self._build = build_fn
        self._service: Any = None
        self._chat_id: Optional[str] = None
        self._page_token: Optional[str] = None
        self._delay = config.YT_MIN_POLL_S
        self.units_spent = 0

    def _charge(self, calls: int = 1) -> None:
        """Account for quota and stop before the ceiling, not after it.

        Args:
            calls: Number of API calls made.

        Raises:
            QuotaExhausted: When the budget is spent.
        """
        self.units_spent += calls * config.YT_UNIT_COST
        if self.units_spent >= config.YT_QUOTA_HARD_STOP:
            raise QuotaExhausted(
                "spent %d of a %d budget (daily allocation %d); stopping before "
                "the ceiling so a rerun is still possible"
                % (self.units_spent, config.YT_QUOTA_HARD_STOP,
                   config.YT_QUOTA_DAILY))

    def open(self) -> None:
        """Build the service and resolve the live chat id, once.

        Raises:
            RuntimeError: If no live chat can be resolved.
        """
        if self._build is not None:
            self._service = self._build()
        else:  # pragma: no cover - requires the Google client
            from googleapiclient.discovery import build

            if self.credentials is not None:
                self._service = build("youtube", "v3",
                                      credentials=self.credentials,
                                      cache_discovery=False)
            else:
                self._service = build("youtube", "v3",
                                      developerKey=self.api_key,
                                      cache_discovery=False)
        self._chat_id = self._resolve_chat_id()
        if not self._chat_id:
            raise RuntimeError("no active live chat found")

    def _resolve_chat_id(self) -> Optional[str]:
        """Fetch the liveChatId once at startup, never per poll.

        Returns:
            The chat id, or None.
        """
        if self.video_id:
            response = self._service.videos().list(
                part="liveStreamingDetails", id=self.video_id).execute()
            self._charge()
            for item in response.get("items", []):
                details = item.get("liveStreamingDetails", {})
                if details.get("activeLiveChatId"):
                    return details["activeLiveChatId"]
            return None
        response = self._service.liveBroadcasts().list(
            part="snippet", mine=True, broadcastStatus="active").execute()
        self._charge()
        for item in response.get("items", []):
            chat_id = item.get("snippet", {}).get("liveChatId")
            if chat_id:
                return chat_id
        return None

    def poll(self) -> List[ChatMessage]:
        """Fetch one page of chat.

        Returns:
            Messages, oldest first.

        Raises:
            QuotaExhausted: When the budget is spent.
        """
        request = self._service.liveChatMessages().list(
            liveChatId=self._chat_id, part="snippet,authorDetails",
            pageToken=self._page_token)
        try:
            response = request.execute()
        except Exception as exc:  # noqa: BLE001 - classify, then re-raise
            text = str(exc).lower()
            if "invalid_grant" in text or "token" in text and "expire" in text:
                self._alert(
                    "YouTube token refresh FAILED (%s). If the OAuth consent "
                    "screen is still in 'Testing', Google revoked the refresh "
                    "token after 7 days -- set it to 'In Production'." % exc)
            raise
        self._charge()
        self._page_token = response.get("nextPageToken")
        self._delay = max(config.YT_MIN_POLL_S,
                          float(response.get("pollingIntervalMillis", 5000)) / 1000.0)

        now = time.monotonic()
        out: List[ChatMessage] = []
        for item in response.get("items", []):
            snippet = item.get("snippet", {})
            author = item.get("authorDetails", {})
            text = snippet.get("displayMessage") or ""
            if not text:
                continue
            out.append(ChatMessage(
                msg_id=str(item.get("id", "")),
                author_id=str(author.get("channelId", "")) or str(
                    author.get("displayName", "")),
                author_name=str(author.get("displayName", "")),
                text=str(text),
                ts=now,
                source=self.name,
            ))
        return out

    def next_poll_delay(self) -> float:
        """The cadence the API asked for, floored.

        Returns:
            Seconds.
        """
        return self._delay


class ChatDownloaderSource(ChatSource):
    """Unofficial reader, for when a token dies ten minutes before doors.

    Uses ``chat-downloader`` (alive; install from git -- the PyPI build is
    stale). Explicitly NOT ``pytchat``, which has been archived and read-only
    since 2021 and is five years dead.

    It scrapes an internal endpoint: no quota, no OAuth, works on any public
    stream, and it will break without warning when YouTube changes the
    continuation-token format. Keep it working; do not make it the default.

    Args:
        url: The watch URL.
        chat_fn: Injected iterator factory, for tests.
    """

    name = "chat-downloader"

    def __init__(self, url: str,
                 chat_fn: Optional[Callable[[str], Iterator[dict]]] = None) -> None:
        self.url = url
        self._chat_fn = chat_fn
        self._iter: Optional[Iterator[dict]] = None
        self._buffer: List[ChatMessage] = []
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def open(self) -> None:
        """Start the reader thread.

        The library's iterator blocks, so it runs on its own thread and hands
        messages over through a lock -- there is no event loop in this process
        at all, deliberately.
        """
        if self._chat_fn is None:  # pragma: no cover - requires the library
            from chat_downloader import ChatDownloader

            self._chat_fn = lambda url: iter(ChatDownloader().get_chat(url))
        self._iter = self._chat_fn(self.url)
        self._thread = threading.Thread(target=self._read_loop, daemon=True,
                                        name="chat-downloader")
        self._thread.start()

    def _read_loop(self) -> None:
        """Pump the blocking iterator into the buffer."""
        try:
            for item in self._iter or []:
                if self._stop.is_set():
                    return
                author = item.get("author", {}) or {}
                text = item.get("message") or ""
                if not text:
                    continue
                msg = ChatMessage(
                    msg_id=str(item.get("message_id", "")),
                    author_id=str(author.get("id", "")) or str(
                        author.get("name", "")),
                    author_name=str(author.get("name", "")),
                    text=str(text),
                    ts=time.monotonic(),
                    source=self.name,
                )
                with self._lock:
                    self._buffer.append(msg)
        except Exception:  # noqa: BLE001 - thread death must not kill the show
            return

    def poll(self) -> List[ChatMessage]:
        """Take what the reader thread has collected.

        Returns:
            Buffered messages.
        """
        with self._lock:
            out, self._buffer = self._buffer, []
        return out

    def next_poll_delay(self) -> float:
        """Cadence.

        Returns:
            One second; the thread does the real work.
        """
        return 1.0

    def close(self) -> None:
        """Stop the reader thread."""
        self._stop.set()


# ---------------------------------------------------------------------------
# Embedded Chat -- the widget on kniteforceradio.com
# ---------------------------------------------------------------------------
# TODO(field-mapping): the key names below are CANDIDATES, not confirmed.
# The site's own handler is minified, so the shape of a ``message`` event was
# never read off a live room -- only that the handshake is
# ``emit("join", "292041")`` then ``on("message", cb)``. Run
#
#     python -m chat_bridge --source embedded --capture-raw logs/embedded_raw.json
#
# for ~15 minutes during a live show, read the key-frequency summary it prints,
# then delete the losing candidates from these tuples and lock the mapper to
# the one true schema. Until that is done, every fallback is logged loudly --
# a source that quietly guesses wrong is worse than one that fails.

#: Candidate keys for the message body, most likely first.
EMBEDDED_TEXT_KEYS: Tuple[str, ...] = (
    "message", "text", "body", "content", "msg",
)
#: Candidate keys whose value is an author OBJECT rather than a name.
EMBEDDED_AUTHOR_KEYS: Tuple[str, ...] = (
    "user", "author", "sender", "from",
)
#: Candidate keys for a display name, either at the top level or inside one of
#: the author objects above.
EMBEDDED_NAME_KEYS: Tuple[str, ...] = (
    "user", "author", "name", "nick", "nickname", "username", "displayName",
    "display_name", "sender",
)
#: Candidate keys for a stable per-viewer id. Only used for the rate limiters;
#: falls back to the display name, exactly as the other sources do.
EMBEDDED_AUTHOR_ID_KEYS: Tuple[str, ...] = (
    "userId", "user_id", "authorId", "author_id", "senderId", "uid", "id",
)
#: The same list minus the bare ``id``, for the TOP level of the payload only.
#: A top-level ``id`` is far more likely to be the message id, and mistaking it
#: for the author id would hand every line a fresh identity -- which silently
#: disables the per-viewer cooldown. Inside a nested ``user`` object, ``id``
#: is unambiguous and stays.
_TOP_AUTHOR_ID_KEYS: Tuple[str, ...] = tuple(
    key for key in EMBEDDED_AUTHOR_ID_KEYS if key != "id")
#: Candidate keys for the platform message id. Dedupe only.
EMBEDDED_MSG_ID_KEYS: Tuple[str, ...] = (
    "messageId", "message_id", "msgId", "msg_id", "_id", "uuid", "id",
)
#: Candidate keys for the platform timestamp. Detected during --capture-raw so
#: the schema can be documented, but deliberately NOT used for
#: ``ChatMessage.ts``: every limiter in the bridge compares against one
#: monotonic clock, and a platform clock would let a replayed or spoofed
#: timestamp reach flow control.
EMBEDDED_TS_KEYS: Tuple[str, ...] = (
    "time", "ts", "timestamp", "createdAt", "created_at", "date", "sentAt",
)


def _coerce_payload(raw: Any) -> Optional[dict]:
    """Reduce whatever the socket handed us to a dict.

    Socket.IO handlers receive the emitted arguments positionally, and a
    provider may send an object, a JSON string, or a bare string.

    Args:
        raw: One handler argument.

    Returns:
        A dict, or None when the payload is not something a message could be
        read out of.
    """
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("{"):
            try:
                parsed = json.loads(text)
            except ValueError:
                return {"text": raw}
            return parsed if isinstance(parsed, dict) else {"text": raw}
        return {"text": raw}
    if isinstance(raw, (list, tuple)) and raw:
        return _coerce_payload(raw[0])
    return None


def _pick(payload: dict, keys: Sequence[str]) -> Tuple[str, Optional[str]]:
    """First scalar value among ``keys``.

    Args:
        payload: The event payload.
        keys: Candidate key names, most likely first.

    Returns:
        ``(value, key)``, or ``("", None)`` when no candidate matched.
    """
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (str, int, float)) and str(value).strip():
            return str(value).strip(), key
    return "", None


def _pick_author(payload: dict) -> Tuple[str, str, Optional[str]]:
    """Find the display name and id, nested author object included.

    Args:
        payload: The event payload.

    Returns:
        ``(name, author_id, matched_key)``. ``matched_key`` is None when
        nothing plausible was found, which the caller must report.
    """
    for key in EMBEDDED_AUTHOR_KEYS:
        nested = payload.get(key)
        if isinstance(nested, dict):
            name, name_key = _pick(nested, EMBEDDED_NAME_KEYS)
            ident, _ = _pick(nested, EMBEDDED_AUTHOR_ID_KEYS)
            if name or ident:
                return name, ident, "%s.%s" % (key, name_key or "id")
    name, name_key = _pick(payload, EMBEDDED_NAME_KEYS)
    ident, _ = _pick(payload, _TOP_AUTHOR_ID_KEYS)
    return name, ident, name_key


def map_embedded_payload(raw: Any, seq: int = 0,
                         warn_fn: Optional[Callable[[str], None]] = None,
                         source_name: str = "embedded-chat",
                         ) -> Optional[ChatMessage]:
    """Best-effort map of one ``message`` event onto a ChatMessage.

    Best-effort, and loud about it. The provider's schema is unconfirmed (see
    the TODO above), so every field that had to fall back is reported through
    ``warn_fn`` rather than silently defaulted.

    Args:
        raw: One handler argument from the ``message`` event.
        seq: Monotonic counter, used only to synthesise a msg_id when the
            payload carries none -- dedupe must not collapse distinct lines.
        warn_fn: Called once per distinct problem. Deduping is the caller's
            job; :class:`EmbeddedChatSource` does it.
        source_name: Value for ``ChatMessage.source``.

    Returns:
        A ChatMessage, or None when there was no text to act on at all.
    """
    warn = warn_fn or (lambda message: None)
    payload = _coerce_payload(raw)
    if payload is None:
        warn("message payload was %s, not an object -- dropped"
             % type(raw).__name__)
        return None

    text, text_key = _pick(payload, EMBEDDED_TEXT_KEYS)
    if not text:
        warn("no text field: tried %s, payload keys were %s"
             % (list(EMBEDDED_TEXT_KEYS), sorted(payload)[:12]))
        return None
    if text_key not in ("message", "text"):
        warn("text read from fallback key %r (expected 'message' or 'text')"
             % text_key)

    name, author_id, author_key = _pick_author(payload)
    if author_key is None:
        warn("no author field: tried %s, payload keys were %s"
             % (list(EMBEDDED_NAME_KEYS), sorted(payload)[:12]))
    if not author_id and name:
        # Same fallback the other sources use: the name becomes the identity.
        # It is weaker -- a renamer gets a fresh cooldown -- but the four gates
        # downstream do not depend on it being strong. Still worth saying out
        # loud, because "per-user limits are weaker than they look" is exactly
        # the kind of thing that should never be discovered mid-set.
        warn("no author id field: falling back to the display name as the "
             "per-viewer identity; cooldowns are per-name, not per-account")
        author_id = name

    msg_id, _ = _pick(payload, EMBEDDED_MSG_ID_KEYS)
    return ChatMessage(
        msg_id=msg_id or "ec-%d" % seq,
        author_id=author_id or "anon",
        author_name=name,
        text=text,
        ts=time.monotonic(),
        source=source_name,
    )


class EmbeddedChatSource(ChatSource):
    """Reads the Kniteforce site's Embedded Chat widget, anonymously.

    The site embeds ``embedded-chat.com``, which speaks Socket.IO v4. Reading
    needs no account: a signed-out client with an empty token connects as
    ``{connected: true, anonymous: true}`` and receives the room's backlog and
    every subsequent line. ``chat-downloader`` does not support the provider,
    hence this reader.

    **Receive-only, structurally.** The client emits exactly one event in its
    whole life -- ``join`` with the room id -- and holds no token, cookie or
    credential. There is no code path here that posts, logs in, or identifies
    itself, and ``tests/test_embedded_chat_source.py`` asserts that against the
    live emit log rather than trusting this paragraph.

    The connection runs on the Socket.IO client's own background thread and
    hands messages over through a lock, so this class keeps the same
    push-into-a-buffer / pull-from-``poll()`` contract as
    :class:`ChatDownloaderSource`. There is no event loop in this process.

    Args:
        room: Room/channel id. Defaults to ``config.EMBEDDED_CHAT_ROOM``.
        url: Origin to connect to.
        client_factory: Builds the Socket.IO client. Injected by the tests; the
            default imports ``socketio`` lazily so the package still imports
            without it installed.
        warn_fn: Operator-visible warning sink. Each distinct message is
            reported once, not once per chat line.
        raw_sink: Called with every raw payload BEFORE mapping. This is how
            ``--capture-raw`` records the true schema. It is never used to feed
            the pipeline -- capture mode does not construct a ChatBridge at
            all, so the gates see nothing.
    """

    name = "embedded-chat"

    def __init__(self, room: str = config.EMBEDDED_CHAT_ROOM,
                 url: str = config.EMBEDDED_CHAT_URL,
                 client_factory: Optional[Callable[[], Any]] = None,
                 warn_fn: Optional[Callable[[str], None]] = None,
                 raw_sink: Optional[Callable[[Any], None]] = None) -> None:
        self.room = str(room)
        self.url = url
        self._client_factory = client_factory
        self._warn = warn_fn or (lambda message: None)
        self._raw_sink = raw_sink
        self._client: Any = None
        self._buffer: Deque[ChatMessage] = collections.deque(
            maxlen=config.EMBEDDED_CHAT_BUFFER_MAX)
        self._lock = threading.Lock()
        self._warned: set = set()
        self._seq = 0
        self.received = 0
        self.mapped = 0
        self.dropped_overflow = 0

    # --- wiring --------------------------------------------------------------

    def _warn_once(self, message: str) -> None:
        """Report a mapping problem the first time it happens.

        Args:
            message: What fell back, in plain English.
        """
        if message in self._warned:
            return
        self._warned.add(message)
        self._warn("embedded-chat: %s" % message)

    def _on_connect(self) -> None:
        """Join the room. Fires on first connect and on every reconnect."""
        self._client.emit("join", self.room)

    def _on_message(self, *args: Any) -> None:
        """Buffer one chat line.

        Runs on the Socket.IO client's background thread.

        Args:
            *args: Whatever the provider emitted with the event.
        """
        payload = args[0] if len(args) == 1 else list(args)
        self.received += 1
        if self._raw_sink is not None:
            try:
                self._raw_sink(payload)
            except Exception as exc:  # noqa: BLE001 - capture must not stop the read
                self._warn_once("raw capture failed: %s" % exc)
        self._seq += 1
        message = map_embedded_payload(payload, seq=self._seq,
                                       warn_fn=self._warn_once,
                                       source_name=self.name)
        if message is None:
            return
        self.mapped += 1
        with self._lock:
            if len(self._buffer) == self._buffer.maxlen:
                self.dropped_overflow += 1
                self._warn_once(
                    "buffer full at %d; oldest lines are being dropped "
                    "(is anything draining poll()?)" % self._buffer.maxlen)
            self._buffer.append(message)

    # --- ChatSource ----------------------------------------------------------

    def open(self) -> None:
        """Connect and join the room.

        Blocking and loud: a provider that is down, or a room id that no longer
        exists, raises here at startup where ``ChatBridge.run`` turns it into an
        operator alert -- rather than presenting as a chat nobody is typing in.

        Raises:
            Exception: Whatever the Socket.IO client raises on a failed connect.
        """
        if self._client_factory is None:  # pragma: no cover - needs the library
            import socketio

            self._client_factory = lambda: socketio.Client(
                reconnection=True, reconnection_delay=1,
                reconnection_delay_max=30)
        self._client = self._client_factory()
        self._client.on("connect", self._on_connect)
        self._client.on("message", self._on_message)
        # Polling first, upgrading to websocket, is what the site's own widget
        # does; forcing websocket-only fails behind some proxies.
        self._client.connect(self.url, transports=["polling", "websocket"],
                             socketio_path="/socket.io")

    def poll(self) -> List[ChatMessage]:
        """Take what the socket thread has collected.

        Returns:
            Buffered messages, oldest first.
        """
        with self._lock:
            out = list(self._buffer)
            self._buffer.clear()
        return out

    def next_poll_delay(self) -> float:
        """Cadence.

        Returns:
            One second; the socket thread does the real work.
        """
        return 1.0

    def close(self) -> None:
        """Disconnect."""
        client, self._client = self._client, None
        if client is None:
            return
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001 - shutdown must not raise
            return


class MergeSource(ChatSource):
    """Fans several sources into one, so a show can read two chats at once.

    ``ChatBridge`` takes a single source and stays that way; this is the seam
    that makes it plural without touching it. Each child keeps its own cadence
    and its own failure mode:

    * a child that raises on ``poll`` is reported once and skipped for that
      tick -- one dead reader must not stop the other one;
    * a child that exhausts its quota is retired permanently, and the alert
      says so. :class:`QuotaExhausted` is deliberately NOT re-raised: on a
      single-source bridge it means "stop", but here it means "YouTube is done,
      the site chat carries the rest of the set";
    * a child that fails to ``open`` is reported and dropped. Only every child
      failing is fatal.

    Messages are tagged: ``msg_id`` and ``author_id`` are prefixed with the
    child's name, so two platforms cannot collide in the dedupe table or in the
    per-viewer cooldowns, and ``source`` names the reader it came from.

    Args:
        sources: The children, in priority order.
        alert_fn: Operator alert sink.
    """

    name = "merge"

    def __init__(self, sources: Sequence[ChatSource],
                 alert_fn: Optional[Callable[[str], None]] = None) -> None:
        if not sources:
            raise ValueError("MergeSource needs at least one source")
        self.sources: List[ChatSource] = list(sources)
        self._alert = alert_fn or (lambda message: None)
        self._dead: set = set()
        self.errors: Dict[str, int] = {}

    def open(self) -> None:
        """Open every child.

        Raises:
            RuntimeError: Only if no child opened at all.
        """
        for source in self.sources:
            try:
                source.open()
            except Exception as exc:  # noqa: BLE001 - one reader, not the show
                self._dead.add(source.name)
                self._alert("merge: source %r failed to open (%s: %s); "
                            "continuing without it"
                            % (source.name, type(exc).__name__, exc))
        if len(self._dead) == len(self.sources):
            raise RuntimeError("no chat source opened: %s"
                               % ", ".join(sorted(self._dead)))

    def poll(self) -> List[ChatMessage]:
        """Poll every live child and interleave the results.

        Returns:
            Every child's messages, tagged with the child that produced them.
        """
        out: List[ChatMessage] = []
        for source in self.sources:
            if source.name in self._dead:
                continue
            try:
                messages = source.poll()
            except QuotaExhausted as exc:
                self._dead.add(source.name)
                self._alert("merge: source %r retired -- %s. The remaining "
                            "sources keep running." % (source.name, exc))
                continue
            except Exception as exc:  # noqa: BLE001 - idle, report, keep going
                count = self.errors.get(source.name, 0) + 1
                self.errors[source.name] = count
                if count in (1, 10, 100):
                    self._alert("merge: source %r poll failed %d time(s) "
                                "(%s: %s)" % (source.name, count,
                                              type(exc).__name__, exc))
                continue
            for message in messages:
                message.source = source.name
                message.msg_id = "%s:%s" % (source.name, message.msg_id)
                message.author_id = "%s:%s" % (source.name, message.author_id)
                out.append(message)
        return out

    def next_poll_delay(self) -> float:
        """The most impatient live child's cadence.

        Returns:
            Seconds. Falls back to the base floor when every child is dead.
        """
        delays = [source.next_poll_delay() for source in self.sources
                  if source.name not in self._dead]
        return min(delays) if delays else config.YT_MIN_POLL_S

    def close(self) -> None:
        """Close every child, whatever any of them think about it."""
        for source in self.sources:
            try:
                source.close()
            except Exception:  # noqa: BLE001 - shutdown must not raise
                continue
