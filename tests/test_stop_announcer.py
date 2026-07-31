"""Closure 4 (2026-07-30): shutdown_djset.sh's --stop-announcer.

The defect: the launcher has been passing `--stop-announcer` on every CLOSE it
owned the announcer for, and this script had no argument parsing at all, so the
flag was silently discarded. CLOSE believed it stopped the announcer; the
announcer kept running. One of the two zombie cases behind the 2026-07-28 gap
report's "State 3: FAILS".

**What these tests deliberately do NOT do: run shutdown_djset.sh.** That script
force-kills TouchDesigner, OBS, Serato and the tracker by design. A test suite
that invokes it would end a live show. So the coverage here is:

  * `stop_announcer()` itself, sourced and run against a real listener the test
    spawns on a scratch port -- the actual kill path, proven end to end;
  * the argument parser, via `--help`, which exits before any teardown;
  * `bash -n` on both files, so a syntax error can't reach the rig.

The full-script behaviour is verified by the operator's ACTIVATE -> CLOSE
receipt, which is the only honest place to verify it.
"""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
STOP_ANNOUNCER = REPO / "lib" / "stop_announcer.sh"
SHUTDOWN = REPO / "shutdown_djset.sh"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_held(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _run_stop_announcer(port: int) -> subprocess.CompletedProcess:
    """Source the two libs and call stop_announcer, exactly as the script does."""
    script = f"""
    source {REPO}/lib/log_json.sh
    source {STOP_ANNOUNCER}
    stop_announcer {port}
    """
    return subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=30
    )


@pytest.fixture
def listener():
    """A stand-in announcer: a real process holding a real port."""
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--bind", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(50):
        if _port_held(port):
            break
        time.sleep(0.1)
    else:
        proc.kill()
        pytest.skip("could not start a test listener")
    yield port, proc
    if proc.poll() is None:
        proc.kill()
        proc.wait(timeout=5)


def test_stop_announcer_kills_the_process_holding_the_port(listener):
    """The core of the fix: identity is the port, not an argv substring. The old
    shape (`pkill -f -- "-m announcer"`) is the Closure 3c self-match defect and
    would not have matched this process at all."""
    port, proc = listener

    result = _run_stop_announcer(port)

    assert proc.poll() is not None, "the listener survived stop_announcer"
    assert not _port_held(port), f":{port} still held"
    assert "stopped serato-obs-announcer" in result.stdout
    assert str(proc.pid) in result.stdout, "the receipt must name the pid it killed"


def test_nothing_listening_is_reported_not_treated_as_failure(capfd):
    """CLOSE runs this on every teardown, including ones where the announcer was
    never started. "Nothing to do" must be a clean, quiet success."""
    port = _free_port()

    result = _run_stop_announcer(port)

    assert result.returncode == 0
    assert "not running" in result.stdout
    assert "CRITICAL" not in result.stdout


def test_a_survivor_is_announced_as_CRITICAL_with_the_launchd_hint(
    listener, monkeypatch
):
    """fail-loud-observability: if the port is still held after SIGKILL,
    something is re-creating the process -- almost certainly a reinstalled
    LaunchAgent. The message must point there rather than leaving the operator
    hunting a process that keeps changing pid."""
    port, proc = listener
    # Neuter `kill` inside the sourced shell so the listener survives, which is
    # the only way to reach the CRITICAL branch without an unkillable process.
    script = f"""
    source {REPO}/lib/log_json.sh
    source {STOP_ANNOUNCER}
    kill() {{ return 0; }}
    stop_announcer {port}
    """
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, timeout=30
    )

    assert result.returncode == 0, "teardown must continue even when a stop fails"
    assert "CRITICAL" in result.stdout
    assert "launchctl list" in result.stdout, "point at the likely cause"
    assert proc.poll() is None


def test_help_documents_the_flag_without_tearing_anything_down():
    """`--help` must exit before the first kill -- both so this test is safe to
    run, and so a mistyped invocation doesn't end a show."""
    result = subprocess.run(
        ["bash", str(SHUTDOWN), "--help"], capture_output=True, text=True, timeout=15
    )

    assert result.returncode == 0
    assert "--stop-announcer" in result.stdout
    assert "shutting down DJ set" not in result.stdout, "teardown started during --help"


@pytest.mark.parametrize("script", [STOP_ANNOUNCER, SHUTDOWN])
def test_scripts_are_syntactically_valid(script):
    """`bash -n` parses without executing. Cheap, and the alternative to finding
    a syntax error at 19:55 is finding it here."""
    result = subprocess.run(
        ["bash", "-n", str(script)], capture_output=True, text=True, timeout=15
    )
    assert result.returncode == 0, result.stderr
