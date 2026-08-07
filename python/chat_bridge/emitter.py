"""The only place this process talks to TouchDesigner.

Everything the audience achieves leaves through here, as a handful of UDP
packets a minute, into the address namespace TouchDesigner gates separately
from Thomas's own buttons.

Two invariants, both asserted by the tests rather than argued for:

1. This module NEVER emits into ``/dj/profile/*``. That namespace is Thomas's,
   and the TD-side kill switch gates only the audience one. If the bridge could
   emit into his namespace, disabling the audience would also disable him.
2. Every address emitted resolves, on the TD side, to a member of a closed set.
   A packet from this process is treated by TouchDesigner exactly as a packet
   from anything else on the LAN would be: re-validated at the airlock.
"""

from __future__ import annotations

from typing import Any, Callable, List, Optional, Sequence, Tuple

from . import config
from .model import Decision


def decision_to_osc(decision: Decision) -> Tuple[str, List[Any]]:
    """Render one decision as an OSC address and argument list.

    Pure, so the wire format is testable without a socket.

    Args:
        decision: A resolved decision.

    Returns:
        ``(address, args)``.

    Raises:
        ValueError: On a verb this function does not know how to send. Raising
            is correct here: an unknown verb reaching the wire means a bug
            upstream, and sending a guess would be worse than crashing loudly.
    """
    if decision.verb == "PROFILE":
        return "%s/profile/%s" % (config.AUDIENCE_PREFIX, decision.target), [1.0]
    if decision.verb == "NUDGE":
        return ("%s/nudge/%s" % (config.AUDIENCE_PREFIX, decision.target),
                [float(decision.amount)])
    if decision.verb == "ONESHOT":
        args: List[Any] = [float(decision.duration)]
        if decision.colour:
            args.append(decision.colour)
        return "%s/oneshot/%s" % (config.AUDIENCE_PREFIX, decision.target), args
    raise ValueError("cannot send verb %r" % decision.verb)


class Emitter:
    """Sends decisions to TouchDesigner over UDP.

    Args:
        host: TD host.
        port: TD's OSC In DAT port.
        send_fn: ``(address, args) -> None``. Injected in tests; defaults to a
            python-osc client created lazily so importing this module needs no
            network stack.
    """

    def __init__(self, host: str = config.TD_OSC_HOST,
                 port: int = config.TD_OSC_PORT,
                 send_fn: Optional[Callable[[str, Sequence[Any]], None]] = None
                 ) -> None:
        self.host = host
        self.port = port
        self._send = send_fn
        self.sent = 0
        self.failed = 0
        self.last_error: Optional[str] = None

    def _client_send(self, address: str, args: Sequence[Any]) -> None:
        """Send via python-osc, building the client on first use.

        Args:
            address: OSC address.
            args: OSC arguments.
        """
        if self._send is None:
            from pythonosc.udp_client import SimpleUDPClient

            client = SimpleUDPClient(self.host, self.port)
            self._send = lambda addr, a: client.send_message(addr, list(a))
        self._send(address, args)

    def send(self, decision: Decision) -> bool:
        """Emit one decision.

        A send failure is counted and logged, never raised: the bridge failing
        to reach TouchDesigner must degrade to "the visuals stop changing".

        Args:
            decision: What to send.

        Returns:
            True if the packet went out.
        """
        address, args = decision_to_osc(decision)
        if not address.startswith(config.AUDIENCE_PREFIX + "/"):
            # Unreachable via decision_to_osc, and that is the point: the
            # assertion is here so any future address that forgets the
            # namespace dies at this line instead of at the rig.
            raise ValueError("refusing to emit outside %s: %s"
                             % (config.AUDIENCE_PREFIX, address))
        try:
            self._client_send(address, args)
        except Exception as exc:  # noqa: BLE001 - degrade, do not raise
            self.failed += 1
            self.last_error = "%s: %s" % (type(exc).__name__, exc)
            return False
        self.sent += 1
        return True
