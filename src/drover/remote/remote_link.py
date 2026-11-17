"""SSH connection + websocket session from this (hub) daemon to one remote drover daemon."""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import time

import aiohttp

from drover.remote.id_prefixing import prefix_ids, strip_ids, tag_machine
from drover.remote.machine_registry import Machine
from drover.remote.remote_bootstrap import ensure_remote_daemon

log = logging.getLogger(__name__)


class RemoteLink:
    def __init__(self, machine: Machine, emit) -> None:
        self.machine = machine
        self.alias = machine.alias
        self.emit = emit  # emit(name, data) on the local hub
        self.status = "connecting"
        self.error = ""
        self.latency_ms: int | None = None
        self.info: dict = {}
        self.snapshot: dict = {}
        self.attempt = 0
        self.retry_at = 0.0
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._ids = itertools.count(1)
        self._pending: dict[int, tuple] = {}  # link id -> (client session, client id) or future
        self._viewers: dict[str, set] = {}  # remote pane id -> local client sessions
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._run_forever())

    def stop(self) -> None:
        if self._task:
            self._task.cancel()

    async def _run_forever(self) -> None:
        while True:
            try:
                await self._connect_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - any network/SSH failure: retry later
                self.status, self.error = "error", str(exc) or exc.__class__.__name__
                log.info("remote %s: %s", self.alias, self.error)
            self.attempt += 1
            delay = min(60, 2 ** min(self.attempt, 6))
            self.retry_at = time.time() + delay
            self.status = "retrying" if self.status != "error" else "error"
            self.emit("state", None)
            await asyncio.sleep(delay)

    async def _connect_once(self) -> None:
        import asyncssh

        user, host = self.machine.user_host
        options = {"username": user, "port": self.machine.port}
        if self.machine.key:
            options["client_keys"] = [self.machine.key]
        if not self.machine.known_hosts:
            options["known_hosts"] = None
        self.status, self.error = "connecting", ""
        self.emit("state", None)
        async with asyncssh.connect(host, **options) as conn:
            info = await ensure_remote_daemon(conn)
            listener = await conn.forward_local_port("127.0.0.1", 0, "127.0.0.1", info["port"])
            url = f"http://127.0.0.1:{listener.get_port()}/ws?token={info['token']}&label=hub"
            async with aiohttp.ClientSession() as http, http.ws_connect(url, heartbeat=20) as ws:
                self._ws, self.attempt, self.status = ws, 0, "connected"
                self.info = info
                pinger = asyncio.create_task(self._ping_loop())
                try:
                    for pane_id in self._viewers:
                        await ws.send_str(json.dumps({"t": "attach", "pane": pane_id}))
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            self._on_message(json.loads(msg.data))
                finally:
                    pinger.cancel()
                    self._ws = None
                    self._fail_pending("connection to " + self.alias + " lost")
        self.status, self.error = "error", "connection closed"

    def _fail_pending(self, message: str) -> None:
        """Answer every in-flight request so no client or `call()` waits forever."""
        pending, self._pending = self._pending, {}
        for waiter in pending.values():
            if isinstance(waiter, asyncio.Future):
                if not waiter.done():
                    waiter.set_exception(ConnectionError(message))
            else:
                session, client_id = waiter
                session.push({"t": "res", "id": client_id, "error": {"code": 1, "message": message}})

    async def _ping_loop(self) -> None:
        while True:
            started = time.time()
            try:
                self.info.update(await self.call("server.info", {}))
                self.latency_ms = int((time.time() - started) * 1000)
                self.emit("machines", None)
            except Exception as exc:  # noqa: BLE001 - any network/SSH failure: retry later
                log.debug("ping %s failed: %s", self.alias, exc)
            await asyncio.sleep(15)

    # -- incoming from remote --------------------------------------------------------
    def _on_message(self, msg: dict) -> None:
        kind = msg.get("t")
        if kind == "ev":
            name, data = msg.get("name"), msg.get("data")
            if name in ("state", "resync"):
                self.snapshot = tag_machine(prefix_ids(data, self.alias), self.alias)
                self.emit("state", None)
            elif name == "pane":
                data = prefix_ids(data, self.alias)
                data["machine"] = self.alias
                self.emit("pane", data)
            elif name in ("status", "policy"):
                self.emit(name, prefix_ids(data, self.alias))
        elif kind in ("out", "replay"):
            pane = msg.get("pane", "")
            relay = {**msg, "pane": f"{self.alias}:{pane}"}
            for session in list(self._viewers.get(pane, ())):
                session.push(relay)
        elif kind == "res":
            waiter = self._pending.pop(msg.get("id"), None)
            if isinstance(waiter, asyncio.Future):
                if not waiter.done():
                    waiter.set_result(msg)
            elif waiter:
                session, client_id = waiter
                reply = {**msg, "id": client_id}
                if "result" in reply:
                    reply["result"] = prefix_ids(reply["result"], self.alias)
                session.push(reply)

    # -- outgoing to remote ------------------------------------------------------------
    async def call(self, method: str, params: dict, timeout: float = 30) -> dict:
        if not self._ws:
            raise ConnectionError(f"{self.alias} is not connected")
        link_id = next(self._ids)
        future = asyncio.get_running_loop().create_future()
        self._pending[link_id] = future
        try:
            await self._ws.send_str(json.dumps({"t": "rpc", "id": link_id, "method": method, "params": params}))
            reply = await asyncio.wait_for(future, timeout)
        finally:
            self._pending.pop(link_id, None)
        if "error" in reply:
            raise RuntimeError(reply["error"].get("message", "remote error"))
        return reply.get("result")

    async def forward(self, session, msg: dict) -> None:
        msg = strip_ids(msg, self.alias)
        kind, pane = msg.get("t"), msg.get("pane", "")
        # Track viewers even while disconnected so a reconnect re-attaches (and replays) for them.
        if kind == "attach":
            self._viewers.setdefault(pane, set()).add(session)
        elif kind == "detach":
            viewers = self._viewers.get(pane, set())
            viewers.discard(session)
            if viewers:
                return  # others still watching: keep the remote stream alive
            self._viewers.pop(pane, None)
        if not self._ws:
            if kind == "rpc":
                session.push({"t": "res", "id": msg.get("id"),
                              "error": {"code": 1, "message": f"{self.alias} is not connected"}})
            return
        if kind == "rpc":
            link_id = next(self._ids)
            self._pending[link_id] = (session, msg.get("id"))
            msg = {**msg, "id": link_id}
        await self._ws.send_str(json.dumps(msg))

    def drop_session(self, session) -> None:
        for viewers in self._viewers.values():
            viewers.discard(session)

    def public(self) -> dict:
        return {"alias": self.alias, "target": self.machine.target, "status": self.status,
                "error": self.error, "latency_ms": self.latency_ms, "retry_at": self.retry_at,
                "attempt": self.attempt, "info": {k: self.info.get(k) for k in ("version", "platform", "uptime")},
                "snapshot": self.snapshot if self.status == "connected" else {}}
