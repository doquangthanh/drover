"""RPC methods for spaces, tabs, layout, restore and search."""

from __future__ import annotations

import asyncio

from herd.core import split_layout_tree as layout
from herd.rpc.rpc_registry import E_BAD_PARAMS, RpcError, need, registry


@registry.method("state.get", "Full snapshot: spaces, tabs, panes, stopped panes", "")
async def state_get(ctx, p: dict) -> dict:
    return ctx.manager.snapshot()


@registry.method("space.create", "Open a folder as a space (starts a shell)", "cwd, command?")
async def space_create(ctx, p: dict) -> dict:
    pane = ctx.manager.create_pane(p.get("command", ""), need(p, "cwd"))
    return {"space_id": pane.meta.space_id, "pane": pane.to_dict()}


@registry.method("space.rename", "Rename a space", "space, name")
async def space_rename(ctx, p: dict) -> None:
    ctx.manager.spaces[need(p, "space")].name = need(p, "name")[:60]
    ctx.manager._changed()


@registry.method("space.remove", "Close a space and all its panes", "space")
async def space_remove(ctx, p: dict) -> None:
    ctx.manager.remove_space(need(p, "space"))


@registry.method("tab.set_layout", "Replace a tab's split tree (from drag-resize)", "tab, layout")
async def tab_set_layout(ctx, p: dict) -> None:
    tab = ctx.manager.tabs[need(p, "tab")]
    new = p.get("layout")
    if not layout.is_valid(new) or sorted(layout.pane_ids(new)) != sorted(layout.pane_ids(tab.layout)):
        raise RpcError(E_BAD_PARAMS, "layout must contain exactly the tab's panes")
    tab.layout = new
    ctx.manager._changed()


@registry.method("tab.rename", "Rename a tab", "tab, name")
async def tab_rename(ctx, p: dict) -> None:
    ctx.manager.tabs[need(p, "tab")].name = need(p, "name")[:60]
    ctx.manager._changed()


@registry.method("tab.zoom", "Toggle zoom of the focused pane", "tab, zoomed")
async def tab_zoom(ctx, p: dict) -> None:
    ctx.manager.tabs[need(p, "tab")].zoomed = bool(p.get("zoomed"))
    ctx.manager._changed()


@registry.method("tab.close", "Close every pane in a tab", "tab")
async def tab_close(ctx, p: dict) -> None:
    tab = ctx.manager.tabs[need(p, "tab")]
    for pane_id in layout.pane_ids(tab.layout):
        if pane_id in ctx.manager.panes:
            ctx.manager.close_pane(pane_id, notify=False)
    ctx.persistence.discard([s["id"] for s in ctx.manager.stopped if s["tab_id"] == tab.id])
    ctx.manager.tabs.pop(tab.id, None)
    ctx.manager._changed()


@registry.method("session.resume", "Restart panes from the previous session", "panes?, fresh?")
async def session_resume(ctx, p: dict) -> list:
    # "panes": [] means "none" (the user unticked everything); only a missing key means "all".
    ids = p["panes"] if "panes" in p else [s["id"] for s in ctx.manager.stopped]
    if not ids:
        return []
    return ctx.persistence.resume(list(ids), use_resume_command=not p.get("fresh"))


@registry.method("session.discard", "Forget panes from the previous session", "panes?")
async def session_discard(ctx, p: dict) -> None:
    ctx.persistence.discard(p.get("panes"))


@registry.method("search.query", "Find agents, spaces and scrollback text", "q")
async def search_query(ctx, p: dict) -> dict:
    q = str(p.get("q", "")).strip().lower()
    m = ctx.manager
    if not q:
        return {"agents": [], "spaces": [], "text": []}
    agents = [pane.to_dict() for pane in m.panes.values()
              if q in pane.meta.name.lower() or q in pane.meta.kind or q in pane.meta.cwd.lower()]
    spaces = [s.to_dict() for s in m.spaces.values() if q in s.name.lower() or q in s.cwd.lower()]
    text = []
    for pane in m.panes.values():
        if len(text) >= 50:
            break
        pane.flush_screen()
        for line_no, line in pane.screen.search(q, limit=min(10, 50 - len(text))):
            text.append({"pane": pane.meta.id, "name": pane.meta.name, "line": line_no, "text": line})
        await asyncio.sleep(0)  # let terminal output flow between panes
    return {"agents": agents[:20], "spaces": spaces[:20], "text": text}


@registry.method("messages.list", "Agent-to-agent actions for the agent tree", "pane?")
async def messages_list(ctx, p: dict) -> list:
    m = ctx.manager
    root = p.get("pane")
    if not root:
        return [msg.to_dict() for msg in m.messages.items][-200:]
    ids, frontier = {root}, [root]
    while frontier:
        children = m.children_of(frontier.pop())
        ids.update(children)
        frontier.extend(children)
    return m.messages.for_tree(ids)[-200:]
