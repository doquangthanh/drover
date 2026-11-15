"""Resolve CLI targets ("%3", "auth", "self", "shop-api/auth") to a local pane id."""

from __future__ import annotations

from drover.core.session_manager import SessionManager
from drover.rpc.rpc_registry import E_BAD_PARAMS, E_NOT_FOUND, RpcError


def resolve_pane(manager: SessionManager, target: str, caller: str | None = None) -> str:
    if not target:
        raise RpcError(E_BAD_PARAMS, "missing target")
    if target == "self":
        if not caller:
            raise RpcError(E_BAD_PARAMS, "'self' only works inside a drover pane")
        target = caller
    target = target.removeprefix("local:")
    if target in manager.panes:
        return target
    space_name, _, name = target.rpartition("/")
    matches = []
    for pane in manager.panes.values():
        if pane.meta.name != name:
            continue
        if space_name:
            space = manager.spaces.get(pane.meta.space_id)
            if not space or space.name != space_name:
                continue
        matches.append(pane.meta.id)
    if not matches:
        raise RpcError(E_NOT_FOUND, f"no agent named '{target}'")
    if len(matches) > 1:
        raise RpcError(E_BAD_PARAMS, f"'{target}' is ambiguous ({', '.join(matches)}); use space/name or id")
    return matches[0]
