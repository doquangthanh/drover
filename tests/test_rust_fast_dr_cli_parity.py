"""The Rust `dr` fast path must print exactly what the Python `dr` prints (agents parse it).

Set DROVER_TEST_FAST_DR_BIN to the Rust dr binary (`cargo build -p drover-cli --no-default-features`). A real
Python daemon runs in the test's private state dir; every case runs through both CLIs and stdout, stderr and the
exit code must match byte for byte. Commands the fast path delegates are checked too (via DROVER_PYTHON_DR).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from daemon_harness import WINDOWS
from external_daemon_harness import ExternalClient, ExternalDaemon, _read_info

FAST_BIN = os.environ.get("DROVER_TEST_FAST_DR_BIN", "").strip()
pytestmark = pytest.mark.skipif(not FAST_BIN, reason="set DROVER_TEST_FAST_DR_BIN to the Rust dr binary")

PYTHON_DR = [sys.executable, "-m", "drover"]
SHELL = "cmd /k echo ready" if WINDOWS else "sh -c 'echo ready; exec sh'"


def python_dr_program() -> str:
    """A single program path for DROVER_PYTHON_DR: the venv's `dr` console script."""
    name = "dr.exe" if WINDOWS else "dr"
    script = Path(sys.executable).with_name(name)
    if not script.is_file():
        pytest.skip(f"{script} missing (uv sync installs the dr console script)")
    return str(script)


def run(cmd: list[str], stdin: bytes | None = None) -> tuple[bytes, bytes, int]:
    env = {**os.environ, "DROVER_PYTHON_DR": python_dr_program()}
    env.pop("DR_PANE_ID", None)
    proc = subprocess.run(cmd, input=stdin or b"", capture_output=True, env=env, timeout=60, check=False)
    return proc.stdout, proc.stderr, proc.returncode


def assert_same(args: list[str], stdin: bytes | None = None, tries: int = 1) -> tuple[bytes, bytes, int]:
    """Python first, then Rust; `tries` > 1 for output with a clock in it (ls AGE can tick between the runs)."""
    for attempt in range(tries):
        expected = run([*PYTHON_DR, *args], stdin)
        got = run([FAST_BIN, *args], stdin)
        if got == expected or attempt == tries - 1:
            break
        time.sleep(0.3)
    assert got == expected, f"dr {args}:\n python={expected!r}\n rust  ={got!r}"
    return got


def start_python_daemon() -> ExternalDaemon:
    """`dr server run` in the test's private state dir. The venv python.exe on Windows is a launcher whose child
    has another pid, so wait for daemon.json itself (the folder is fresh) instead of matching the pid."""
    state = Path(os.environ["DROVER_STATE_DIR"])
    log = open(state / "external-daemon.log", "ab")  # noqa: SIM115 - owned by the child process
    proc = subprocess.Popen([*PYTHON_DR, "server", "run"], stdout=log, stderr=log, stdin=subprocess.DEVNULL)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        info = _read_info(state / "daemon.json")
        if info and info.get("port"):
            return ExternalDaemon(proc, ExternalClient(f"http://127.0.0.1:{info['port']}"), info["token"])
        time.sleep(0.1)
    proc.kill()
    raise AssertionError(f"daemon did not start; see {state / 'external-daemon.log'}")


async def wait_ready(daemon, pane: str) -> None:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        _, body = await daemon.call("pane.read", {"pane": pane})
        if "ready" in body.get("result", {}).get("text", ""):
            return
        await asyncio.sleep(0.2)
    raise AssertionError(f"pane {pane} never printed 'ready'")


async def test_fast_commands_print_exactly_like_python(drover_dirs: Path) -> None:
    daemon = start_python_daemon()
    panes: list[str] = []
    try:
        for name in ("worker", "tiếng-việt", "doomed-1", "doomed-2"):
            _, body = await daemon.call("pane.create", {"command": SHELL, "name": name, "cwd": str(drover_dirs)})
            panes.append(body["result"]["id"])
        for pane in panes:
            await wait_ready(daemon, pane)
        worker = panes[0]

        # read-only first, so both CLIs see the same screen
        assert_same(["ls"], tries=3)
        assert_same(["ls", "--json"])
        assert_same(["ls", "--names"])
        assert_same(["read", worker])
        assert_same(["read", "worker", "--lines", "3"])
        assert_same(["read", worker, "--json"])
        assert_same(["wait-output", worker, "ready", "--timeout", "5"])
        assert_same(["wait-output", worker, "rea.y", "--regex", "--json", "--lines=40"])
        assert_same(["wait", worker, "--timeout", "5", "--state", "idle", "--state", "done"])
        assert_same(["wait", "--children", "all", "--timeout", "1"])
        assert_same(["wait", "--children", "any", "--timeout", "1"])

        # errors and usage
        assert_same(["wait"])
        assert_same(["read", "no-such-agent"])
        assert_same(["kill", "no-such-agent"])
        assert_same(["send", "no-such-agent", "hi"])

        # same effect twice is fine: these print the same line each time
        assert_same(["send", worker, "echo one", "--no-enter"])
        assert_same(["keys", worker, "esc"])
        assert_same(["rename", panes[1], "tiếng-việt"])
        assert_same(["prompt", worker, "-", "--timeout", "5"], stdin=b"echo hai\r\n")

        # delegated to Python unchanged
        assert_same(["ls", "--help"])
        assert_same(["send", worker])
        assert_same(["read", worker, "--lin", "2"])
        assert_same(["templates"])

        # kill acts once per pane: each CLI stops its own one, both must print nothing and exit 0
        assert run([*PYTHON_DR, "kill", panes[2]]) == run([FAST_BIN, "kill", panes[3], "--tree"]) == (b"", b"", 0)
        del panes[2:]
        assert_same(["ls", "--json"])
    finally:
        for pane in panes:
            await daemon.call("pane.close", {"pane": pane})
        run([*PYTHON_DR, "server", "stop"])  # the real daemon process, not just the venv launcher
        await daemon.shutdown()

    # no daemon: --names prints nothing on both
    assert run([FAST_BIN, "ls", "--names"]) == run([*PYTHON_DR, "ls", "--names"]) == (b"", b"", 0)
