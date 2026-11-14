"""Boot the real daemon app (build_context + build_app) inside the test loop.

Uses aiohttp's TestServer/TestClient directly (pytest-aiohttp is not installed).
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import time
from dataclasses import dataclass
from typing import Any

from aiohttp.test_utils import TestClient, TestServer

from herd.daemon.daemon_main import build_context
from herd.daemon.web_server import build_app


@dataclass
class Daemon:
    ctx: Any
    client: TestClient
    token: str
    monitor: asyncio.Task

    async def call(self, method: str, params: dict | None = None, token: str | None = None) -> tuple[int, Any]:
        """POST /rpc. Returns (http status, parsed JSON body or text for non-JSON replies)."""
        auth = self.token if token is None else token
        resp = await self.client.post(
            "/rpc", json={"method": method, "params": params or {}},
            headers={"Authorization": f"Bearer {auth}"})
        if resp.content_type == "application/json":
            return resp.status, await resp.json()
        return resp.status, await resp.text()

    async def shutdown(self) -> None:
        for pane in list(self.ctx.manager.panes.values()):
            pane.kill(wait=True)
        self.monitor.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.monitor
        await self.client.close()


async def wait_for_text(daemon: Daemon, pane_id: str, needle: str, timeout: float = 20.0) -> str:
    """Poll pane.read until `needle` shows up on the pane's screen or scrollback."""
    deadline = time.monotonic() + timeout
    text = ""
    while time.monotonic() < deadline:
        status, body = await daemon.call("pane.read", {"pane": pane_id})
        if status == 200 and "result" in body:
            text = body["result"]["text"]
            if needle in text:
                return text
        await asyncio.sleep(0.25)
    raise AssertionError(f"{needle!r} not seen in pane {pane_id} after {timeout}s. Screen:\n{text}")


async def boot_daemon() -> Daemon:
    token = secrets.token_urlsafe(32)
    ctx = build_context(token)
    ctx.notifier.enabled = False  # no desktop toasts from the test run
    ctx.persistence.load_previous()
    client = TestClient(TestServer(build_app(ctx)))
    await client.start_server()
    monitor = asyncio.create_task(ctx.monitor.run())  # same loop the daemon runs in
    return Daemon(ctx=ctx, client=client, token=token, monitor=monitor)
