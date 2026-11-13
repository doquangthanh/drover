"""Method registry for the daemon's JSON-RPC API (shared by websocket UI and HTTP CLI)."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

# Error codes surfaced to the CLI as exit codes where it makes sense.
E_GENERAL, E_TIMEOUT, E_NOT_FOUND, E_POLICY, E_BAD_PARAMS = 1, 2, 3, 4, 5
E_NO_METHOD = -32601


class RpcError(Exception):
    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code, self.message, self.data = code, message, data

    def to_dict(self) -> dict:
        out = {"code": self.code, "message": self.message}
        if self.data is not None:
            out["data"] = self.data
        return out


Handler = Callable[[Any, dict], Awaitable[Any]]


@dataclass
class MethodSpec:
    name: str
    doc: str
    params: str
    handler: Handler


class RpcRegistry:
    def __init__(self) -> None:
        self.methods: dict[str, MethodSpec] = {}

    def method(self, name: str, doc: str, params: str = "") -> Callable[[Handler], Handler]:
        def wrap(fn: Handler) -> Handler:
            self.methods[name] = MethodSpec(name, doc, params, fn)
            return fn

        return wrap

    async def call(self, ctx: Any, name: str, params: dict | None) -> Any:
        spec = self.methods.get(name)
        if spec is None:
            raise RpcError(E_NO_METHOD, f"unknown method {name}")
        try:
            return await spec.handler(ctx, params or {})
        except RpcError:
            raise
        except KeyError as exc:
            raise RpcError(E_NOT_FOUND, f"not found: {exc.args[0] if exc.args else exc}") from exc
        except (ValueError, TypeError) as exc:
            raise RpcError(E_BAD_PARAMS, str(exc)) from exc
        except Exception as exc:
            log.exception("rpc %s failed", name)
            raise RpcError(E_GENERAL, str(exc) or exc.__class__.__name__) from exc

    def schema(self) -> dict:
        return {
            "openrpc": "1.2.6",
            "info": {"title": "herd daemon", "version": "1"},
            "methods": [{"name": s.name, "summary": s.doc, "params": s.params}
                        for s in sorted(self.methods.values(), key=lambda s: s.name)],
        }


registry = RpcRegistry()


def need(params: dict, key: str, kind: type = str) -> Any:
    if key not in params or params[key] in (None, ""):
        raise RpcError(E_BAD_PARAMS, f"missing parameter: {key}")
    value = params[key]
    if not isinstance(value, kind):
        raise RpcError(E_BAD_PARAMS, f"{key} must be {kind.__name__}")
    return value
