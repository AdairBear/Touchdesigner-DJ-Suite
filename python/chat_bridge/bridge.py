"""The run loop that wires the stages together, and the degradation ladder.

Deliberately synchronous. There is no ``asyncio`` anywhere in this package: the
one blocking reader that needs a thread gets a plain daemon thread, and every
client lives on the thread that created it. That sidesteps the loop-bound
client landmine outright rather than guarding against it.

The degradation ladder, which is the whole reason this design is worth its
complexity:

===========================  =================================================
LLM slow or erroring         skip the batch. NEVER queue pending batches --
                             a queue is how an outage becomes a stampede at
                             recovery.
Moderation erroring          fail closed, alert after 3 consecutive.
Quota exhausted / stream up  idle, log, keep the last state.
Bridge process dies          TD stops receiving packets. The look freezes at
                             whatever was last applied, which is always a
                             validated look.
Bridge sends garbage         rejected at the TD airlock.
===========================  =================================================

Every one of those ends at "the visuals stop changing", never at "the visuals
break". That is a consequence of the enum, not of care taken here.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from . import config, prefilter
from .arbiter import Arbiter, Intake
from .emitter import Emitter
from .interpreter import Interpreter
from .moderation import Moderator
from .model import Decision
from .sources import ChatSource, QuotaExhausted


class NdjsonLog:
    """Append-only structured log.

    Independent of every network transport in this process on purpose: the
    alert path must survive the failure it is reporting, so it writes to a
    local file and to stderr, and never through OSC or HTTP.

    Args:
        path: Destination file. Its directory is created if missing.
    """

    def __init__(self, path: str = config.LOG_PATH) -> None:
        self.path = path
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        self._lock = threading.Lock()
        self._t0 = time.monotonic()

    def write(self, event: str, **fields: Any) -> None:
        """Append one record.

        Args:
            event: Record type.
            **fields: Arbitrary JSON-serialisable fields.
        """
        record: Dict[str, Any] = {
            "ts": time.time(),
            "offset": round(time.monotonic() - self._t0, 3),
            "event": event,
        }
        record.update(fields)
        line = json.dumps(record, ensure_ascii=True, default=str)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def alert(self, message: str) -> None:
        """Raise an operator alert: loud on stderr, and on the record.

        Args:
            message: What went wrong, in plain English.
        """
        self.write("alert", level="CRITICAL", message=message)
        sys.stderr.write("\n!!! CHAT BRIDGE ALERT: %s\n\n" % message)
        sys.stderr.flush()


class ChatBridge:
    """Reads chat, decides at most one thing every half minute, emits OSC.

    Args:
        source: Where chat comes from.
        interpreter: Classifier. Defaults to a live OpenAI one.
        moderator: Moderation stack. Defaults to a live OpenAI one.
        emitter: OSC out. Defaults to a live python-osc client.
        log: Structured log.
        arbiter: Flow control. Injected in tests to preload state.
    """

    def __init__(self, source: ChatSource,
                 interpreter: Optional[Interpreter] = None,
                 moderator: Optional[Moderator] = None,
                 emitter: Optional[Emitter] = None,
                 log: Optional[NdjsonLog] = None,
                 arbiter: Optional[Arbiter] = None) -> None:
        self.source = source
        self.log = log or NdjsonLog()
        self.interpreter = interpreter or Interpreter()
        self.moderator = moderator or Moderator(alert_fn=self.log.alert)
        self.emitter = emitter or Emitter()
        self.arbiter = arbiter or Arbiter()
        self.intake = Intake()

        self._stop = threading.Event()
        self._next_poll = 0.0
        self._next_batch = 0.0
        self._next_heartbeat = 0.0
        self.batches = 0
        self.emitted = 0

    # --- operator control ----------------------------------------------------

    def on_control(self, address: str, *args: Any) -> None:
        """Handle a control message sent to the bridge's own port.

        This is the bridge-side half of the kill switch. The TD-side half is
        independent: TouchOSC is configured to send to both, so neither gate
        depends on the other process being healthy.

        Args:
            address: OSC address.
            *args: OSC arguments.
        """
        now = time.monotonic()
        value = float(args[0]) if args and isinstance(args[0], (int, float)) else 1.0
        if address.endswith("/enable"):
            self.arbiter.enabled = bool(value)
            self.log.write("control", control="enable", value=self.arbiter.enabled)
        elif address.endswith("/gain"):
            self.arbiter.gain = max(0.0, min(1.0, value))
            self.log.write("control", control="gain", value=self.arbiter.gain)
        elif address.endswith("/lock_profile"):
            self.arbiter.lock_profile = bool(value)
            self.log.write("control", control="lock_profile",
                           value=self.arbiter.lock_profile)
        elif address.startswith("/dj/panic"):
            self.arbiter.panic(now)
            self.log.write("control", control="panic",
                           lockout_s=config.PANIC_LOCKOUT_S)
        elif address.startswith(config.OPERATOR_PREFIX):
            # Thomas touched a profile button. His action wins and keeps
            # winning, so pending votes do not flip it back eight seconds later.
            self.arbiter.arm_lockout(now)
            self.log.write("control", control="operator_profile",
                           address=address, lockout_s=config.OPERATOR_LOCKOUT_S)

    def start_control_listener(self) -> Optional[Any]:
        """Bind the control port on a daemon thread.

        Returns:
            The server, or None if python-osc is unavailable -- in which case
            the TD-side kill switch is still fully functional, and that is
            logged rather than being allowed to look like success.
        """
        try:
            from pythonosc.dispatcher import Dispatcher
            from pythonosc.osc_server import ThreadingOSCUDPServer
        except ImportError:
            self.log.write("warn", message="python-osc missing: bridge-side "
                                           "control port not listening")
            return None
        dispatcher = Dispatcher()
        dispatcher.set_default_handler(self.on_control)
        server = ThreadingOSCUDPServer(("0.0.0.0", config.BRIDGE_CONTROL_PORT),
                                       dispatcher)
        threading.Thread(target=server.serve_forever, daemon=True,
                         name="bridge-control").start()
        self.log.write("listening", port=config.BRIDGE_CONTROL_PORT)
        return server

    # --- pipeline ------------------------------------------------------------

    def ingest(self, now: float) -> int:
        """Poll the source and admit messages.

        Args:
            now: Monotonic seconds.

        Returns:
            How many were admitted.
        """
        try:
            messages = self.source.poll()
        except QuotaExhausted as exc:
            self.log.alert("YouTube quota budget spent: %s" % exc)
            self._stop.set()
            return 0
        except Exception as exc:  # noqa: BLE001 - idle, log, keep last state
            self.log.write("source_error", error="%s: %s" % (type(exc).__name__, exc))
            self._next_poll = now + 5.0
            return 0

        admitted = 0
        for msg in messages:
            if self.intake.offer(msg, now):
                admitted += 1
                self.log.write("message", msg_id=msg.msg_id,
                               author_id=msg.author_id,
                               author_name=msg.author_name, text=msg.text,
                               source=msg.source)
        self._next_poll = now + self.source.next_poll_delay()
        return admitted

    def run_batch(self, now: float) -> List[Decision]:
        """Moderate, classify, validate and tally one batch.

        Args:
            now: Monotonic seconds.

        Returns:
            One-shot decisions ready to send immediately. Profile and nudge
            decisions wait for the vote window.
        """
        self.batches += 1
        raw = self.intake.drain()
        if not raw:
            return self.arbiter.take_oneshots(now)

        candidates = prefilter.dedupe(prefilter.prefilter(raw))
        if not candidates:
            self.log.write("batch", size=len(raw), prefiltered=0)
            return self.arbiter.take_oneshots(now)

        passed, rejected = self.moderator.check_batch(candidates)
        for author_id, reason in rejected:
            self.log.write("moderation_reject", author_id=author_id, reason=reason)

        actions, reasons = self.interpreter.classify(passed)
        for reason in reasons:
            self.log.write("validator_reject", reason=reason)

        outcomes: Dict[str, str] = {}
        for action in actions:
            status = self.arbiter.offer(action, now)
            outcomes[action.key()] = status
            self.log.write("action", verb=action.verb, target=action.target,
                           amount=round(action.amount, 3),
                           colour=action.colour,
                           confidence=round(action.confidence, 2),
                           author=action.safe_name, status=status)

        self.log.write("batch", size=len(raw), prefiltered=len(candidates),
                       moderated=len(passed), actions=len(actions),
                       rejects=len(reasons))
        return self.arbiter.take_oneshots(now)

    def emit(self, decisions: List[Decision]) -> None:
        """Send decisions and record what went out.

        Args:
            decisions: What to send.
        """
        for decision in decisions:
            ok = self.emitter.send(decision)
            self.emitted += int(ok)
            self.log.write("emit", verb=decision.verb, target=decision.target,
                           amount=round(decision.amount, 3),
                           colour=decision.colour,
                           duration=round(decision.duration, 3),
                           votes=decision.votes, author=decision.safe_name,
                           sent=ok, error=self.emitter.last_error if not ok else None)

    def tick(self, now: float) -> None:
        """Advance the clock by one step.

        Args:
            now: Monotonic seconds.
        """
        if now >= self._next_poll:
            self.ingest(now)
        if now >= self._next_batch:
            self._next_batch = now + config.BATCH_S
            self.emit(self.run_batch(now))
        if self.arbiter.window_due(now):
            decisions, tally = self.arbiter.resolve(now)
            self.log.write("window", tally=tally, decided=len(decisions),
                           locked_out=self.arbiter.locked_out(now),
                           enabled=self.arbiter.enabled)
            self.emit(decisions)
        if now >= self._next_heartbeat:
            self._next_heartbeat = now + config.HEARTBEAT_S
            self.log.write(
                "heartbeat", queued=len(self.intake),
                batches=self.batches, emitted=self.emitted,
                llm_calls=self.interpreter.calls,
                llm_failures=self.interpreter.failures,
                mod_errors=self.moderator.total_errored,
                dropped_rate=self.intake.dropped_rate,
                dropped_overflow=self.intake.dropped_overflow,
                counters=dict(self.arbiter.counters),
                enabled=self.arbiter.enabled, gain=self.arbiter.gain)

    def run(self, duration_s: Optional[float] = None,
            sleep_fn: Callable[[float], None] = time.sleep) -> None:
        """Run until stopped.

        Args:
            duration_s: Optional wall-clock limit, for soak runs.
            sleep_fn: Injected for tests.
        """
        self.log.write("start", source=self.source.name,
                       td="%s:%d" % (self.emitter.host, self.emitter.port))
        try:
            self.source.open()
        except Exception as exc:  # noqa: BLE001 - a source that will not open
            self.log.alert("chat source failed to open: %s: %s"
                           % (type(exc).__name__, exc))
            return
        self.start_control_listener()
        started = time.monotonic()
        try:
            while not self._stop.is_set():
                now = time.monotonic()
                if duration_s is not None and now - started >= duration_s:
                    break
                self.tick(now)
                sleep_fn(config.TICK_S)
        except KeyboardInterrupt:
            pass
        finally:
            self.source.close()
            self.log.write("stop", batches=self.batches, emitted=self.emitted)

    def stop(self) -> None:
        """Ask the run loop to finish."""
        self._stop.set()
