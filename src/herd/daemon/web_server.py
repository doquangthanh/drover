"""HTTP + WebSocket front door: serves the UI, the websocket session and JSON-RPC for the CLI."""

from __future__ import annotations

import hmac
import json
import logging

from aiohttp import web

from herd.app_paths import web_static_dir
from herd.daemon.ws_client_session import WsClientSession
from herd.rpc.rpc_registry import RpcError, registry

log = logging.getLogger(__name__)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def _token_ok(ctx, supplied: str | None) -> bool:
    # Compare bytes: compare_digest raises TypeError on non-ASCII str (would turn a 401 into a 500).
    return bool(supplied) and hmac.compare_digest(supplied.encode("utf-8"), ctx.token.encode("utf-8"))


async def _call_remote(ctx, alias: str, method: str, params: dict):
    from herd.remote.id_prefixing import prefix_ids, strip_ids

    link = ctx.remotes.links[alias]
    timeout = float(params.get("timeout", 25)) + 5
    remote_params = strip_ids(params, alias)
    if params.get("caller"):
        # Keep the policy in force remotely: mark the call as coming from an agent on the hub.
        remote_params["caller"] = f"hub:{params['caller']}"
    return prefix_ids(await link.call(method, remote_params, timeout=timeout), alias)


def build_app(ctx) -> web.Application:
    app = web.Application(client_max_size=4 * 1024 * 1024)
    static = web_static_dir()

    async def index(request: web.Request) -> web.StreamResponse:
        # The page itself is harmless; every data channel below requires the token.
        return web.FileResponse(static / "index.html", headers=SECURITY_HEADERS)

    async def ws_handler(request: web.Request) -> web.StreamResponse:
        if not _token_ok(ctx, request.query.get("token")):
            raise web.HTTPUnauthorized(text="bad token")
        ws = web.WebSocketResponse(heartbeat=25, max_msg_size=4 * 1024 * 1024)
        await ws.prepare(request)
        label = request.query.get("label", "browser")[:40]
        await WsClientSession(ctx, ws, label).run()
        return ws

    async def rpc_handler(request: web.Request) -> web.StreamResponse:
        auth = request.headers.get("Authorization", "")
        if not _token_ok(ctx, auth.removeprefix("Bearer ").strip()):
            raise web.HTTPUnauthorized(text="bad token")
        try:
            body = await request.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return web.json_response({"error": {"code": 5, "message": "invalid JSON"}}, status=400)
        if not isinstance(body, dict) or not isinstance(body.get("params") or {}, dict):
            return web.json_response({"error": {"code": 5, "message": "expected {method, params}"}}, status=400)
        method, params = str(body.get("method")), body.get("params") or {}
        try:
            routed = str(params.get("machine") or params.get("pane") or "")
            if ctx.remotes and ctx.remotes.owns(routed):
                result = await _call_remote(ctx, routed.split(":", 1)[0], method, params)
            else:
                result = await registry.call(ctx, method, params)
            return web.json_response({"result": result})
        except RpcError as exc:
            return web.json_response({"error": exc.to_dict()})
        except (ConnectionError, RuntimeError, TimeoutError) as exc:
            return web.json_response({"error": {"code": 1, "message": str(exc)}})

    async def health(request: web.Request) -> web.StreamResponse:
        return web.json_response({"ok": True, "app": "herd"})

    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    app.router.add_post("/rpc", rpc_handler)
    app.router.add_get("/health", health)
    app.router.add_static("/static/", static, show_index=False)
    return app
