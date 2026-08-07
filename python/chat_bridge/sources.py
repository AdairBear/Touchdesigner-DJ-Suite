"""Chat ingestion, behind one interface so the reader is swappable.

Four implementations of one seam:

``YouTubeAPISource``   official Data API v3. OAuth for Thomas's own channel, a
                       plain API key for anyone else's public stream. Honours
                       the ``pollingIntervalMillis`` the API returns, never a
                       hardcoded cadence, and hard-stops on a quota budget.
``ChatDownloaderSource`` the escape hatch. No auth, no quota, no Cloud project
                       -- valuable in exactly one scenario, which is a token
                       dying ten minutes before doors. Unofficial and it will
                       break without warning, so it is not the default.
``ReplaySource``       reads an NDJSON log back. This is what makes an offline
                       rehearsal of a real stream possible.
``ListSource``         a list of messages. Tests.

The quota arithmetic deserves a warning: Google's quota table does not document
the live-streaming endpoints at all, so the per-call cost is UNKNOWN. Watch the
Cloud Console graph during the first stream and set ``CHAT_BRIDGE_UNIT_COST``
to what you measure. The default of 1 is the likely value, not a verified one.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable, Iterable, Iterator, List, Optional

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
