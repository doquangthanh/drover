"""One websocket to the daemon for the whole TUI (plain asyncio + aiohttp, no Textual, so it is easy to test).

Protocol: see `drover.daemon.ws_client_session`. Reconnects with backoff and re-attaches the panes that were attached.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
from collections.abc import Callable
from typing import Any

import aiohttp

log = logging.getLogger(__name__)
RPC_TIMEOUT = 30.0
BACKOFF_START, BACKOFF_MAX = 0.5, 5.0


class RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def _noop(*_args: Any) -> None:
    return None


class DaemonConnection:
    """Callbacks (set by the app): on_state(state), on_status(data), on_pane(pane), on_output(pane, data, is_replay),
    on_connection(connected). `on_output` is the hot path: it is called directly, never through Textual messages."""

    def __init__(self, base_url: str, token: str, label: str = "dr-tui") -> None:
        self._ws_url = f"{base_url.rstrip('/')}/ws"
        self._params = {"token": token, "label": label}
        self.on_state: Callable[[dict], None] = _noop
        self.on_status: Callable[[dict], None] = _noop
        self.on_pane: Callable[[dict], None] = _noop
        self.on_output: Callable[[str, str, bool], None] = _noop
        self.on_connection: Callable[[bool], None] = _noop
        self.connected = False
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._attached: set[str] = set()
        self._stopping = False

    # -- public API -----------------------------------------------------------------
    async def rpc(self, method: str, params: dict | None = None) -> Any:
        if self._ws is None:
            raise RpcError(-1, "not connected to the daemon")
        rid = next(self._ids)
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[rid] = future
        try:
            await self._send({"t": "rpc", "id": rid, "method": method, "params": params or {}})
            return await asyncio.wait_for(future, RPC_TIMEOUT)
        except TimeoutError as exc:
            raise RpcError(-1, f"{method} timed out") from exc
        finally:
            self._pending.pop(rid, None)

    def send_input(self, pane: str, data: str) -> None:
        self._fire({"t": "in", "pane": pane, "data": data})

    def attach(self, pane: str) -> None:
        self._attached.add(pane)
        self._fire({"t": "attach", "pane": pane})

    def detach(self, pane: str) -> None:
        self._attached.discard(pane)
        self._fire({"t": "detach", "pane": pane})

    def stop(self) -> None:
        self._stopping = True
        if self._ws is not None:
            asyncio.ensure_future(self._ws.close())

    # -- connection loop ------------------------------------------------------------
    async def run(self) -> None:
        backoff = BACKOFF_START
        async with aiohttp.ClientSession() as http:
            while not self._stopping:
                try:
                    async with http.ws_connect(self._ws_url, params=self._params, max_msg_size=0) as ws:
                        backoff = BACKOFF_START
                        await self._session(ws)
                except (aiohttp.ClientError, OSError) as exc:
                    log.debug("daemon connection failed: %s", exc)
                self._set_connected(False)
                self._fail_pending()
                if self._stopping:
                    return
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, BACKOFF_MAX)

    async def _session(self, ws: aiohttp.ClientWebSocketResponse) -> None:
        self._ws = ws
        self._set_connected(True)
        for pane in sorted(self._attached):  # re-attach after a reconnect: the daemon answers with a fresh replay
            await self._send({"t": "attach", "pane": pane})
        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    self._dispatch(json.loads(msg.data))
                elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSED):
                    break
        finally:
            self._ws = None

    def _dispatch(self, msg: dict) -> None:
        kind = msg.get("t")
        if kind in ("out", "replay"):
            self.on_output(str(msg["pane"]), msg["data"], kind == "replay")
        elif kind == "res":
            future = self._pending.get(msg.get("id"))
            if future and not future.done():
                error = msg.get("error")
                if error:
                    future.set_exception(RpcError(int(error.get("code", 1)), str(error.get("message", ""))))
                else:
                    future.set_result(msg.get("result"))
        elif kind == "ev":
            name, data = msg.get("name"), msg.get("data")
            if name in ("state", "resync"):  # resync = the daemon dropped events for us: full state again
                self.on_state(data)
            elif name == "status":
                self.on_status(data)
            elif name == "pane":
                self.on_pane(data)

    # -- helpers --------------------------------------------------------------------
    async def _send(self, msg: dict) -> None:
        if self._ws is not None and not self._ws.closed:
            await self._ws.send_str(json.dumps(msg))

    def _fire(self, msg: dict) -> None:
        """Send from sync code. Tasks start in creation order, so keystrokes keep their order."""
        if self._ws is not None and not self._ws.closed:
            task = asyncio.ensure_future(self._send(msg))
            task.add_done_callback(lambda t: t.cancelled() or t.exception())  # a closing socket is not an error here

    def _set_connected(self, value: bool) -> None:
        if self.connected != value:
            self.connected = value
            self.on_connection(value)

    def _fail_pending(self) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_exception(RpcError(-1, "connection to the daemon was lost"))
        self._pending.clear()


async def wait_connected(conn: DaemonConnection, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not conn.connected:
        if asyncio.get_running_loop().time() > deadline:
            raise TimeoutError("daemon connection not ready")
        await asyncio.sleep(0.02)


__all__ = ["DaemonConnection", "RpcError", "wait_connected"]
