"""One websocket client (the drover UI, a phone browser, or a hub daemon) talking to this daemon.

Client -> daemon:
  {"t":"rpc","id":1,"method":"pane.create","params":{...}}
  {"t":"in","pane":"%3","data":"ls\\r"}              fast-path keystrokes
  {"t":"attach","pane":"%3"} / {"t":"detach","pane":"%3"}
Daemon -> client:
  {"t":"res","id":1,"result":...} | {"t":"res","id":1,"error":{code,message}}
  {"t":"ev","name":"state"|"pane"|"status"|"policy"|"machines","data":...}
  {"t":"out","pane":"%3","data":"..."} and {"t":"replay","pane":"%3","data":"..."}
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging

from aiohttp import WSMsgType, web

from drover.core.event_hub import BoundedQueue
from drover.remote.id_prefixing import foreign_ids, route_of
from drover.rpc.rpc_registry import RpcError, registry

log = logging.getLogger(__name__)
_client_ids = itertools.count(1)


class WsClientSession:
    def __init__(self, ctx, ws: web.WebSocketResponse, label: str) -> None:
        self.ctx = ctx
        self.ws = ws
        self.id = next(_client_ids)
        self.label = label
        self.out = BoundedQueue()
        self.attached: set[str] = set()
        self._out_buf: dict[str, list[str]] = {}
        self._tasks: set[asyncio.Task] = set()

    async def run(self) -> None:
        ctx = self.ctx
        ctx.clients[self.id] = {"id": self.id, "label": self.label}
        unsubscribe = ctx.hub.subscribe(self._on_event)
        sender = asyncio.create_task(self._sender())
        self.out.put({"t": "ev", "name": "state", "data": ctx.combined_state()})
        try:
            async for msg in self.ws:
                if msg.type == WSMsgType.TEXT:
                    await self._handle(json.loads(msg.data))
                elif msg.type == WSMsgType.ERROR:
                    break
        except (json.JSONDecodeError, ConnectionResetError) as exc:
            log.debug("ws client %s closed: %s", self.id, exc)
        finally:
            unsubscribe()
            for pane_id in list(self.attached):
                self._detach(pane_id)
            if ctx.remotes:
                for link in ctx.remotes.links.values():
                    link.drop_session(self)
            sender.cancel()
            ctx.clients.pop(self.id, None)

    def _on_event(self, name: str, data) -> None:
        if name == "state":
            data = self.ctx.combined_state()
        self.out.put({"t": "ev", "name": name, "data": data})

    def _on_output(self, pane_id: str, data: str) -> None:
        # Coalesce chunks that arrive in the same loop iteration into one websocket message.
        if pane_id in self._out_buf:
            self._out_buf[pane_id].append(data)
            return
        self._out_buf[pane_id] = [data]
        asyncio.get_running_loop().call_soon(self._flush_output, pane_id)

    def _flush_output(self, pane_id: str) -> None:
        parts = self._out_buf.pop(pane_id, None)
        if parts:
            self.out.put({"t": "out", "pane": pane_id, "data": "".join(parts)})

    async def _sender(self) -> None:
        while True:
            item = await self.out.get()
            if item.get("t") == "resync":
                item = {"t": "ev", "name": "resync", "data": self.ctx.combined_state()}
            await self.ws.send_str(json.dumps(item))

    async def _handle(self, msg: dict) -> None:
        kind = msg.get("t")
        pane_id = str(msg.get("pane", ""))
        remotes = self.ctx.remotes
        params = msg.get("params") or {}
        routed = pane_id or route_of(params)
        if remotes and remotes.owns(routed):
            mixed = foreign_ids(params, routed.split(":", 1)[0]) if kind == "rpc" else []
            if mixed:
                err = RpcError(5, f"ids from different machines in one call ({', '.join(mixed)})")
                self.out.put({"t": "res", "id": msg.get("id"), "error": err.to_dict()})
                return
            await remotes.forward_from_client(self, {**msg, "pane": msg.get("pane") or routed}
                                              if kind != "rpc" else {**msg, "_route": routed})
            return
        if kind == "in":
            pane = self.ctx.manager.panes.get(pane_id)
            if pane:
                pane.write(str(msg.get("data", "")))
        elif kind == "attach":
            self._attach(pane_id)
        elif kind == "detach":
            self._detach(pane_id)
        elif kind == "rpc":
            self._spawn_rpc(msg)

    def _spawn_rpc(self, msg: dict) -> None:
        task = asyncio.create_task(self._rpc(msg))
        self._tasks.add(task)  # keep a reference so the task isn't garbage-collected mid-flight
        task.add_done_callback(self._tasks.discard)

    async def _rpc(self, msg: dict) -> None:
        try:
            result = await registry.call(self.ctx, str(msg.get("method")), msg.get("params") or {})
            reply = {"t": "res", "id": msg.get("id"), "result": result}
        except RpcError as exc:
            reply = {"t": "res", "id": msg.get("id"), "error": exc.to_dict()}
        self.out.put(reply)

    def _attach(self, pane_id: str) -> None:
        pane = self.ctx.manager.panes.get(pane_id)
        if not pane:
            return
        # Always replay (also on re-attach after a resync/reconnect) so the viewer is never blank.
        self._out_buf.pop(pane_id, None)
        self.out.put({"t": "replay", "pane": pane_id, "data": pane.replay_text()})
        if pane_id not in self.attached:
            self.attached.add(pane_id)
            pane.output_listeners.add(self._on_output)

    def _detach(self, pane_id: str) -> None:
        self.attached.discard(pane_id)
        pane = self.ctx.manager.panes.get(pane_id)
        if pane:
            pane.output_listeners.discard(self._on_output)

    def push(self, item: dict) -> None:
        """Used by the remote hub to relay messages from another machine."""
        self.out.put(item)
