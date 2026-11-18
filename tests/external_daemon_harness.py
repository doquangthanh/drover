"""Run the daemon tests against an external daemon binary (conformance mode).

Set DROVER_TEST_DAEMON_BIN to a `dr`-compatible executable (the Python `dr` or the Rust rewrite). Each test then
starts `<bin> server run` as a subprocess inside the test's private DROVER_STATE_DIR / DROVER_CONFIG_DIR, reads
daemon.json for port + token, and talks to it over real HTTP. Tests that reach into the Python internals
(`daemon.ctx`) are skipped in this mode.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

import aiohttp
import pytest
from yarl import URL

BIN_ENV = "DROVER_TEST_DAEMON_BIN"
START_TIMEOUT = 20.0


def external_bin() -> list[str] | None:
    raw = os.environ.get(BIN_ENV, "").strip()
    return shlex.split(raw) if raw else None


class ExternalClient:
    """The bits of aiohttp's TestClient the tests use (get, post, make_url, close), over a real session."""

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.session = aiohttp.ClientSession(base_url=base_url)

    def get(self, path: str, **kwargs):
        return self.session.get(path, **kwargs)

    def post(self, path: str, **kwargs):
        return self.session.post(path, **kwargs)

    def make_url(self, path: str) -> URL:
        return URL(self.base_url).join(URL(path))

    async def close(self) -> None:
        await self.session.close()


class ExternalDaemon:
    """Same surface as daemon_harness.Daemon (call, client, token, shutdown), minus the in-process ctx."""

    def __init__(self, proc: subprocess.Popen, client: ExternalClient, token: str) -> None:
        self.proc, self.client, self.token = proc, client, token

    @property
    def ctx(self) -> Any:
        pytest.skip("reads in-process daemon internals; not available against an external daemon binary")

    async def call(self, method: str, params: dict | None = None, token: str | None = None) -> tuple[int, Any]:
        auth = self.token if token is None else token
        async with self.client.post(
                "/rpc", json={"method": method, "params": params or {}},
                headers={"Authorization": f"Bearer {auth}"}) as resp:
            if resp.content_type == "application/json":
                return resp.status, await resp.json()
            return resp.status, await resp.text()

    async def shutdown(self) -> None:
        await self.client.close()
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()


async def boot_external_daemon(cmd: list[str]) -> ExternalDaemon:
    state_dir = Path(os.environ["DROVER_STATE_DIR"])  # set per test by conftest.drover_dirs
    info_path = state_dir / "daemon.json"
    log = open(state_dir / "external-daemon.log", "ab")  # noqa: SIM115 - owned by the child process
    proc = subprocess.Popen([*cmd, "server", "run"], stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                            env=dict(os.environ))
    deadline = time.monotonic() + START_TIMEOUT
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise AssertionError(f"daemon exited with {proc.returncode}; see {state_dir / 'external-daemon.log'}")
        info = _read_info(info_path)
        if info and info.get("pid") == proc.pid:
            client = ExternalClient(f"http://127.0.0.1:{info['port']}")
            return ExternalDaemon(proc, client, info["token"])
        await asyncio.sleep(0.1)
    proc.kill()
    raise AssertionError(f"daemon did not write {info_path} within {START_TIMEOUT}s")


def _read_info(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
