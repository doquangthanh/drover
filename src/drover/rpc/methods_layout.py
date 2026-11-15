"""RPC methods that shape the layout from scripts: new tabs, split, move, swap, zoom and share of a split.

Every method returns the ids it created or touched so a caller never has to guess them.
"""

from __future__ import annotations

from drover.core import split_layout_tree as layout
from drover.core.orchestration_policy import PolicyError
from drover.rpc.methods_panes import _pane
from drover.rpc.rpc_registry import E_BAD_PARAMS, E_POLICY, RpcError, need, registry

DIRECTIONS = {"right": "row", "down": "col", "row": "row", "col": "col"}


def _direction(p: dict) -> str:
    value = str(p.get("direction") or "right")
    if value not in DIRECTIONS:
        raise RpcError(E_BAD_PARAMS, "direction must be right or down")
    return DIRECTIONS[value]


def _spawn(ctx, p: dict, cwd: str, **where):
    """create_pane with the caller as parent; a refused spawn is a policy error (code 4) like pane.create."""
    parent = p.get("caller") if p.get("caller") in ctx.manager.panes else None
    try:
        return ctx.manager.create_pane(p.get("command", ""), cwd, p.get("name", ""), parent=parent, **where)
    except PolicyError as exc:
        raise RpcError(E_POLICY, str(exc)) from exc


@registry.method("tab.create", "New tab in a space with a shell or command", "space, command?, name?")
async def tab_create(ctx, p: dict) -> dict:
    m = ctx.manager
    space = m.spaces[need(p, "space")]
    tab = m.create_tab(space.id, str(p.get("name") or "tab")[:60])
    try:
        pane = _spawn(ctx, p, space.cwd, tab_id=tab.id)
    except BaseException:
        m.tabs.pop(tab.id, None)  # don't leave an empty tab behind
        raise
    if not p.get("name"):
        tab.name = pane.meta.name
    return {"tab": tab.to_dict(), "pane": pane.to_dict()}


@registry.method("pane.split", "Split a pane and start a shell or command beside it",
                 "pane, direction?: right|down, command?, name?, cwd?")
async def pane_split(ctx, p: dict) -> dict:
    m = ctx.manager
    target = m.get(_pane(ctx, p))
    pane = _spawn(ctx, p, p.get("cwd") or target.meta.cwd, tab_id=target.meta.tab_id, split_from=target.meta.id,
                  direction=_direction(p))
    return {"pane": pane.to_dict()}


@registry.method("pane.move", "Move a pane into another tab (or a new tab)", "pane, tab? | new_tab?, direction?")
async def pane_move(ctx, p: dict) -> dict:
    m = ctx.manager
    pane = m.get(_pane(ctx, p))
    direction = _direction(p)  # validate everything before the pane leaves its tab
    if p.get("new_tab"):
        target = m.create_tab(pane.meta.space_id, pane.meta.name)
    else:
        target = m.tabs[need(p, "tab")]
        if target.id == pane.meta.tab_id:
            raise RpcError(E_BAD_PARAMS, "pane is already in that tab")
    previous_tab = pane.meta.tab_id
    m.detach_from_tab(pane)
    target.layout = layout.insert(target.layout, target.focused, pane.meta.id, direction)
    target.focused = pane.meta.id
    pane.meta.tab_id, pane.meta.space_id = target.id, target.space_id
    m._changed()
    return {"pane": pane.to_dict(), "tab": target.to_dict(), "previous_tab": previous_tab}


@registry.method("pane.swap", "Swap two panes' places (same or different tabs)", "pane, target")
async def pane_swap(ctx, p: dict) -> dict:
    m = ctx.manager
    a, b = m.get(_pane(ctx, p)), m.get(_pane(ctx, p, "target"))
    if a is b:
        raise RpcError(E_BAD_PARAMS, "cannot swap a pane with itself")
    tab_a, tab_b = m.tabs[a.meta.tab_id], m.tabs[b.meta.tab_id]
    for tab in {tab_a.id: tab_a, tab_b.id: tab_b}.values():
        tab.layout = layout.swap_leaves(tab.layout, a.meta.id, b.meta.id)
        if tab.focused in (a.meta.id, b.meta.id) and tab_a is not tab_b:
            tab.focused = b.meta.id if tab.focused == a.meta.id else a.meta.id
    a.meta.tab_id, b.meta.tab_id = b.meta.tab_id, a.meta.tab_id
    a.meta.space_id, b.meta.space_id = b.meta.space_id, a.meta.space_id
    m._changed()
    return {"panes": [a.to_dict(), b.to_dict()]}


@registry.method("pane.zoom", "Zoom a pane to fill its tab (zoomed=false restores)", "pane, zoomed?")
async def pane_zoom(ctx, p: dict) -> dict:
    m = ctx.manager
    pane = m.get(_pane(ctx, p))
    tab = m.tabs[pane.meta.tab_id]
    tab.focused, tab.zoomed = pane.meta.id, bool(p.get("zoomed", True))
    m._changed()
    return {"tab": tab.to_dict()}


@registry.method("pane.share", "Set how much of its split a pane takes (0.1-0.9)", "pane, share")
async def pane_share(ctx, p: dict) -> dict:
    m = ctx.manager
    pane = m.get(_pane(ctx, p))
    share = p.get("share")
    if not isinstance(share, (int, float)) or not 0.1 <= share <= 0.9:
        raise RpcError(E_BAD_PARAMS, "share must be a number from 0.1 to 0.9")
    tab = m.tabs[pane.meta.tab_id]
    tab.layout = layout.set_share(tab.layout, pane.meta.id, float(share))
    m._changed()
    return {"tab": tab.to_dict()}
