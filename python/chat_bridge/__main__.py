"""Command line entry point.

    python -m chat_bridge --source replay --file logs/chat_bridge.ndjson --dry-run
    python -m chat_bridge --source youtube
    python -m chat_bridge --source fallback --url https://youtube.com/watch?v=...
    python -m chat_bridge --source embedded --room 292041
    python -m chat_bridge --source merge --video-id ... --room 292041

``--dry-run`` is the important one: it runs the whole pipeline and logs every
decision without opening a socket to TouchDesigner. That is how the interpreter
gets reviewed against a real stream before it is ever allowed near the show.

``--capture-raw`` is the other one, and it is not a bridge run at all: it
connects to Embedded Chat, writes the raw ``message`` payloads to a file, and
never builds a pipeline. No moderation, no interpreter, no OSC, no key needed.
It exists because the provider's payload schema is unconfirmed -- see the TODO
in :mod:`chat_bridge.sources`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Sequence

from . import config
from .bridge import ChatBridge, NdjsonLog
from .emitter import Emitter
from .interpreter import Interpreter
from .moderation import Moderator
from .sources import (EMBEDDED_TS_KEYS, ChatDownloaderSource, ChatSource,
                      EmbeddedChatSource, MergeSource, ReplaySource,
                      YouTubeAPISource)

#: Scope for reading live chat. Deliberately NOT youtube.force-ssl, which would
#: also permit POSTING into chat -- the bridge must never be able to speak.
YT_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


def _oauth_credentials(client_secrets: str, token_path: str) -> Any:
    """Load or obtain OAuth credentials for the owner's own live chat.

    Args:
        client_secrets: Path to the Desktop-app client secrets JSON.
        token_path: Where the refresh token is cached.

    Returns:
        A google-auth credentials object.
    """
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow

    creds = None
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, YT_SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(client_secrets, YT_SCOPES)
        creds = flow.run_local_server(port=0)
    with open(token_path, "w", encoding="utf-8") as handle:
        handle.write(creds.to_json())
    return creds


def build_source(args: argparse.Namespace, log: NdjsonLog) -> ChatSource:
    """Construct the chat source the flags asked for.

    Args:
        args: Parsed arguments.
        log: For the loud token-refresh alert.

    Returns:
        An unopened ChatSource.
    """
    if args.source == "replay":
        return ReplaySource(args.file, realtime=args.realtime)
    if args.source == "fallback":
        return ChatDownloaderSource(args.url)
    if args.source == "embedded":
        return _embedded_source(args, log)
    if args.source == "merge":
        return MergeSource([_embedded_source(args, log),
                            _youtube_source(args, log, allow_url=True)],
                           alert_fn=log.alert)
    return _youtube_source(args, log)


def _embedded_source(args: argparse.Namespace, log: NdjsonLog) -> ChatSource:
    """Build the site-chat reader.

    Args:
        args: Parsed arguments.
        log: Warnings go on the record, not just to stderr -- an unconfirmed
            field mapping falling back is exactly the thing that must not be
            discovered by noticing the visuals never moved.

    Returns:
        An unopened EmbeddedChatSource.
    """
    return EmbeddedChatSource(
        room=args.room,
        warn_fn=lambda message: log.write("warn", source="embedded-chat",
                                          message=message))


def _youtube_source(args: argparse.Namespace, log: NdjsonLog,
                    allow_url: bool = False) -> ChatSource:
    """Build the YouTube reader the flags describe.

    Args:
        args: Parsed arguments.
        log: For the loud token-refresh alert.
        allow_url: Whether ``--url`` may select the unofficial reader. True
            only for ``--source merge``, which has no other way to say "and
            this stream, without a Cloud project". ``--source youtube`` keeps
            meaning the official API and nothing else.

    Returns:
        An unopened source.
    """
    if allow_url and args.url:
        return ChatDownloaderSource(args.url)
    credentials = None
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not args.video_id:
        credentials = _oauth_credentials(args.client_secrets, args.token)
    return YouTubeAPISource(video_id=args.video_id, credentials=credentials,
                            api_key=api_key, alert_fn=log.alert)


def capture_raw(room: str, path: str, duration_s: Optional[float] = None,
                source: Optional[EmbeddedChatSource] = None,
                sleep_fn: Any = time.sleep) -> int:
    """Record raw Embedded Chat payloads to a file, feeding nothing.

    Run this for ten or fifteen minutes during a live show, then read the key
    summary it prints at the end. That summary is what turns the candidate key
    lists in :mod:`chat_bridge.sources` into a locked mapper.

    Nothing downstream exists in this mode: no moderation, no interpreter, no
    arbiter, no emitter, no socket to TouchDesigner. The four gates are not
    weakened here, they are simply not in the process.

    Args:
        room: Room/channel id.
        path: Where to write the pretty-printed payloads.
        duration_s: Stop after this many seconds. None runs until Ctrl-C.
        source: Injected source, for tests.
        sleep_fn: Injected sleep, for tests.

    Returns:
        Process exit code.
    """
    seen: Dict[str, int] = {}
    handle = open(path, "a", encoding="utf-8")
    count = [0]

    def sink(payload: Any) -> None:
        """Write one payload and count its keys.

        Args:
            payload: The raw event argument.
        """
        count[0] += 1
        handle.write("\n// ---- message %d @ %s ----\n"
                     % (count[0], time.strftime("%H:%M:%S")))
        handle.write(json.dumps(payload, indent=2, ensure_ascii=False,
                                default=str))
        handle.write("\n")
        handle.flush()
        if isinstance(payload, dict):
            for key in payload:
                seen[key] = seen.get(key, 0) + 1

    reader = source or EmbeddedChatSource(
        room=room, raw_sink=sink,
        warn_fn=lambda message: sys.stderr.write("  warn: %s\n" % message))
    if source is not None:
        source._raw_sink = sink  # noqa: SLF001 - test seam, deliberate

    sys.stderr.write(
        "capture-raw: room %s -> %s\n"
        "  This does NOT drive graphics. Nothing is moderated, interpreted or\n"
        "  emitted. Leave it running ~15 min of a busy show, then Ctrl-C.\n"
        % (room, path))
    try:
        reader.open()
    except Exception as exc:  # noqa: BLE001 - report, do not traceback at a gig
        sys.stderr.write("capture-raw: could not connect: %s: %s\n"
                         % (type(exc).__name__, exc))
        handle.close()
        return 1

    started = time.monotonic()
    try:
        while duration_s is None or time.monotonic() - started < duration_s:
            reader.poll()          # drain, so the bounded buffer never fills
            sleep_fn(1.0)
    except KeyboardInterrupt:
        pass
    finally:
        reader.close()
        handle.close()

    sys.stderr.write("\ncapture-raw: %d message events written to %s\n"
                     % (count[0], path))
    if seen:
        sys.stderr.write("  top-level keys seen (count):\n")
        for key, hits in sorted(seen.items(), key=lambda kv: -kv[1]):
            note = "  <-- timestamp candidate" if key in EMBEDDED_TS_KEYS else ""
            sys.stderr.write("    %-20s %6d%s\n" % (key, hits, note))
        sys.stderr.write(
            "  Now lock the mapper: edit EMBEDDED_*_KEYS in "
            "chat_bridge/sources.py down to the keys above.\n")
    else:
        sys.stderr.write(
            "  NO events captured. Either the room was silent, or the "
            "handshake/event name has changed -- do not assume it worked.\n")
    return 0


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse the command line.

    Args:
        argv: Argument vector, defaulting to ``sys.argv[1:]``.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        prog="chat_bridge",
        description="Audience chat -> TouchDesigner graphics, through a closed enum.")
    parser.add_argument("--source", default="youtube",
                        choices=["youtube", "fallback", "replay", "embedded",
                                 "merge"],
                        help="youtube = official API (default); fallback = "
                             "chat-downloader, no auth; replay = an NDJSON log; "
                             "embedded = the Kniteforce site chat widget; "
                             "merge = the site chat AND YouTube together")
    parser.add_argument("--room", default=config.EMBEDDED_CHAT_ROOM,
                        help="Embedded Chat room id (default %(default)s)")
    parser.add_argument("--capture-raw", default=None, metavar="PATH",
                        help="record raw Embedded Chat payloads to PATH and "
                             "exit. Feeds nothing: no moderation, no "
                             "interpreter, no OSC. Use it to confirm the "
                             "provider's field names during a live show.")
    parser.add_argument("--video-id", default=None,
                        help="public video id; omit to read your own active "
                             "broadcast, which requires OAuth")
    parser.add_argument("--url", default=None, help="watch URL, for --source fallback")
    parser.add_argument("--file", default=config.LOG_PATH,
                        help="NDJSON log, for --source replay")
    parser.add_argument("--realtime", action="store_true",
                        help="replay at the original message spacing")
    parser.add_argument("--client-secrets", default="client_secrets.json")
    parser.add_argument("--token", default=os.path.expanduser("~/.chat_bridge_token.json"))
    parser.add_argument("--dry-run", action="store_true",
                        help="run everything, send nothing to TouchDesigner")
    parser.add_argument("--no-moderation", action="store_true",
                        help="offline replay only; logged as a degraded run")
    parser.add_argument("--duration", type=float, default=None,
                        help="stop after N seconds (soak runs)")
    parser.add_argument("--log", default=config.LOG_PATH)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the bridge.

    Args:
        argv: Argument vector.

    Returns:
        Process exit code.
    """
    args = parse_args(argv)

    if args.capture_raw:
        # Before every other check on purpose: capture mode builds no
        # pipeline, so it needs no OPENAI_API_KEY and touches no gate.
        return capture_raw(args.room, args.capture_raw, duration_s=args.duration)

    log = NdjsonLog(args.log)

    if args.source == "fallback" and not args.url:
        sys.stderr.write("--source fallback needs --url\n")
        return 2
    if not os.environ.get("OPENAI_API_KEY"):
        sys.stderr.write(
            "OPENAI_API_KEY is not set. The interpreter and the moderation "
            "layer both need it; without it every batch fails closed and the "
            "visuals will simply never change.\n")
        return 2

    sent: List[Any] = []
    emitter = Emitter(send_fn=(lambda a, g: sent.append((a, list(g))))
                      if args.dry_run else None)
    if args.dry_run:
        log.write("warn", message="DRY RUN: no packets will reach TouchDesigner")
    if args.no_moderation:
        log.write("warn", message="DEGRADED: hosted moderation disabled by flag")

    bridge = ChatBridge(
        source=build_source(args, log),
        interpreter=Interpreter(),
        moderator=Moderator(alert_fn=log.alert, enabled=not args.no_moderation),
        emitter=emitter,
        log=log,
    )
    bridge.run(duration_s=args.duration)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
