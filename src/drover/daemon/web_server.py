"""HTTP + WebSocket front door: serves the UI, the websocket session and JSON-RPC for the CLI."""

from __future__ import annotations

import hmac
import json
import logging

from aiohttp import web

from drover.app_paths import web_static_dir
from drover.daemon.web_ui_routes import add_ui_routes
from drover.daemon.ws_client_session import WsClientSession
from drover.remote.id_prefixing import route_of
from drover.rpc.rpc_registry import RpcError, registry

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
    from drover.remote.id_prefixing import foreign_ids, prefix_ids, strip_ids

    mixed = foreign_ids(params, alias)
    if mixed:
        raise RpcError(5, f"ids from different machines in one call ({', '.join(mixed)}); use ids on {alias}")
    link = ctx.remotes.links[alias]
    timeout = float(params.get("timeout", 25)) + 5
    remote_params = strip_ids(params, alias)
    if params.get("caller"):
        # Keep the policy in force remotely: mark the call as coming from an agent on the hub.
        remote_params["caller"] = f"hub:{params['caller']}"
    return prefix_ids(await link.call(method, remote_params, timeout=timeout), alias)


# Large enough for a chat message carrying pictures (methods_chat.MAX_IMAGES_B64); everything needs the token anyway.
MAX_MESSAGE_BYTES = 24 * 1024 * 1024


def build_app(ctx) -> web.Application:
    app = web.Application(client_max_size=MAX_MESSAGE_BYTES)

    async def ws_handler(request: web.Request) -> web.StreamResponse:
        if not _token_ok(ctx, request.query.get("token")):
            raise web.HTTPUnauthorized(text="bad token")
        ws = web.WebSocketResponse(heartbeat=25, max_msg_size=MAX_MESSAGE_BYTES)
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
            routed = route_of(params)
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
        return web.json_response({"ok": True, "app": "drover"})

    app.router.add_get("/ws", ws_handler)
    app.router.add_post("/rpc", rpc_handler)
    app.router.add_get("/health", health)
    # Icons, ace and favicon stay as plain files; the UI itself is the built bundle (see web_ui_routes).
    app.router.add_static("/static/", web_static_dir(), show_index=False)
    add_ui_routes(app, SECURITY_HEADERS)
    return app
