"""Command line entry point.

    python -m chat_bridge --source replay --file logs/chat_bridge.ndjson --dry-run
    python -m chat_bridge --source youtube
    python -m chat_bridge --source fallback --url https://youtube.com/watch?v=...

``--dry-run`` is the important one: it runs the whole pipeline and logs every
decision without opening a socket to TouchDesigner. That is how the interpreter
gets reviewed against a real stream before it is ever allowed near the show.
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, List, Optional, Sequence

from . import config
from .bridge import ChatBridge, NdjsonLog
from .emitter import Emitter
from .interpreter import Interpreter
from .moderation import Moderator
from .sources import (ChatDownloaderSource, ChatSource, ReplaySource,
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
    credentials = None
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not args.video_id:
        credentials = _oauth_credentials(args.client_secrets, args.token)
    return YouTubeAPISource(video_id=args.video_id, credentials=credentials,
                            api_key=api_key, alert_fn=log.alert)


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
                        choices=["youtube", "fallback", "replay"],
                        help="youtube = official API (default); fallback = "
                             "chat-downloader, no auth; replay = an NDJSON log")
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
