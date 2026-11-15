"""RPC methods that act on panes: create, input, read, wait, close."""

from __future__ import annotations

import asyncio
import itertools
import time

from drover.core.orchestration_policy import OrchestrationPolicy, PolicyError
from drover.git import worktree_service as wt
from drover.rpc.rpc_registry import E_BAD_PARAMS, E_POLICY, E_TIMEOUT, RpcError, need, registry
from drover.rpc.target_resolver import resolve_pane

_answer_ids = itertools.count(1)
TERMINAL_STATES = {"exited"}


def _pane(ctx, params: dict, key: str = "pane") -> str:
    return resolve_pane(ctx.manager, str(params.get(key, "")), params.get("caller"))


@registry.method("pane.create", "Start an agent or shell", "command?, cwd?, name?, tab_id?, split_from?, "
                 "direction?, caller?, worktree?: {task, base?}, cols?, rows?")
async def pane_create(ctx, p: dict) -> dict:
    cwd = p.get("cwd") or ""
    if p.get("worktree"):
        info = await wt.create_worktree(cwd or ".", p["worktree"]["task"], p["worktree"].get("base", ""))
        cwd = info["path"]
    caller = p.get("caller") if p.get("caller") in ctx.manager.panes else None
    try:
        pane = ctx.manager.create_pane(
            p.get("command", ""), cwd, p.get("name", ""), tab_id=p.get("tab_id"),
            split_from=p.get("split_from"), direction=p.get("direction", "row"), parent=caller,
            cols=int(p.get("cols", 120)), rows=int(p.get("rows", 32)))
    except PolicyError as exc:
        raise RpcError(E_POLICY, str(exc)) from exc
    return pane.to_dict()


@registry.method("pane.write", "Raw keystrokes from the UI", "pane, data")
async def pane_write(ctx, p: dict) -> None:
    if p.get("caller"):
        raise RpcError(E_POLICY, "agents must use pane.send (dr send), not raw pane.write")
    ctx.manager.get(need(p, "pane")).write(str(p.get("data", "")))


def _mark_busy(ctx, pane) -> None:
    """New input = new turn. Leave done/idle at once so a following `dr wait` waits for *this* turn."""
    if pane.state in ("done", "idle"):
        old = pane.state
        tracker = pane.tracker
        tracker.state, tracker.since, tracker._candidate = "working", time.time(), None
        tracker.hold_until = time.time() + 3
        pane.unread = False
        ctx.hub.emit("pane", pane.to_dict())
        ctx.hub.emit("status", {"pane": pane.to_dict(), "old": old, "new": "working"})


@registry.method("pane.send", "Type text into an agent (as `dr send`)", "pane, text, enter?, caller?")
async def pane_send(ctx, p: dict) -> dict:
    pane_id = _pane(ctx, p)
    pane = ctx.manager.get(pane_id)
    text = str(p.get("text", ""))
    data = text + ("\r" if p.get("enter", True) else "")
    caller = p.get("caller")
    policy = OrchestrationPolicy.from_settings(ctx.settings.get("orchestration", {}))
    if caller and caller != pane_id and not policy.may_agent_answer(pane.state):
        if policy.answer_prompts == "never":
            raise RpcError(E_POLICY, "agents may not answer permission prompts (policy: never)")
        answer_id = f"a{next(_answer_ids)}"
        ctx.pending_answers[answer_id] = (pane_id, data, caller)
        ctx.manager.messages.add("denied", caller, pane_id, text)
        ctx.hub.emit("policy", {"id": answer_id, "source": caller, "target": pane_id, "text": text})
        ctx.hub.emit("state", None)
        raise RpcError(E_POLICY, "target is waiting on a permission prompt; forwarded to the user")
    pane.write(data)
    if p.get("enter", True):
        _mark_busy(ctx, pane)
    if caller:
        ctx.manager.messages.add("send", caller, pane_id, text)
    return {"pane": pane_id}


@registry.method("policy.decide", "Allow or deny an agent's answer to a prompt (user only)", "id, allow")
async def policy_decide(ctx, p: dict) -> None:
    if p.get("caller"):
        raise RpcError(E_POLICY, "only the user can decide; agents may not approve answers")
    pane_id, data, caller = ctx.pending_answers.pop(need(p, "id"))
    if p.get("allow") and pane_id in ctx.manager.panes:
        ctx.manager.get(pane_id).write(data)
        ctx.manager.messages.add("send", caller, pane_id, data.strip())
    ctx.hub.emit("state", None)


@registry.method("pane.resize", "Resize the pseudo-terminal", "pane, cols, rows")
async def pane_resize(ctx, p: dict) -> None:
    cols, rows = p.get("cols"), p.get("rows")
    if not isinstance(cols, (int, float)) or not isinstance(rows, (int, float)):
        raise RpcError(E_BAD_PARAMS, "cols and rows must be numbers")
    ctx.manager.get(need(p, "pane")).resize(int(cols), int(rows))


@registry.method("pane.read", "Plain text of a pane (scrollback + screen)", "pane, lines?")
async def pane_read(ctx, p: dict) -> dict:
    pane_id = _pane(ctx, p)
    lines = int(p["lines"]) if p.get("lines") else None
    if p.get("caller"):
        ctx.manager.messages.add("read", p["caller"], pane_id, f"{lines or 'all'} lines")
    pane = ctx.manager.get(pane_id)
    pane.flush_screen()
    return {"pane": pane_id, "text": pane.screen.read_text(lines)}


@registry.method("pane.wait", "Block until a pane reaches a state", "pane, states?, timeout?")
async def pane_wait(ctx, p: dict) -> dict:
    pane_id = _pane(ctx, p)
    wanted = set(p.get("states") or ["done", "idle", "blocked"]) | TERMINAL_STATES
    timeout = float(p.get("timeout", 600))
    pane = ctx.manager.get(pane_id)
    if p.get("caller"):
        ctx.manager.messages.add("wait", p["caller"], pane_id, ",".join(sorted(wanted - TERMINAL_STATES)))
    # "idle" is the starting state of every pane, so only a *transition* into idle counts.
    if pane.state in wanted and pane.state != "idle":
        return {"pane": pane_id, "state": pane.state}
    future = asyncio.get_running_loop().create_future()

    def listener(name, data):
        if name == "status" and data["pane"]["id"] == pane_id and data["new"] in wanted and not future.done():
            future.set_result(data["new"])

    unsubscribe = ctx.hub.subscribe(listener)
    try:
        state = await asyncio.wait_for(future, timeout)
    except TimeoutError as exc:
        raise RpcError(E_TIMEOUT, f"timed out after {timeout:.0f}s; state is {pane.state}") from exc
    finally:
        unsubscribe()
    return {"pane": pane_id, "state": state}


@registry.method("pane.close", "Stop a pane and remove it from its tab", "pane, subtree?")
async def pane_close(ctx, p: dict) -> None:
    pane_id = _pane(ctx, p)
    if p.get("subtree"):
        for child in ctx.manager.children_of(pane_id):
            await pane_close(ctx, {"pane": child, "subtree": True})
    ctx.manager.close_pane(pane_id)


@registry.method("pane.restart", "Restart a pane (optionally with its resume command)", "pane, resume?")
async def pane_restart(ctx, p: dict) -> dict:
    pane = ctx.manager.get(_pane(ctx, p))
    meta = pane.meta
    command = (meta.resume if p.get("resume", True) else "") or meta.command
    new = ctx.manager.create_pane(command if meta.kind != "shell" else "", meta.cwd, meta.name,
                                  tab_id=meta.tab_id, split_from=meta.id, parent=meta.parent)
    ctx.manager.close_pane(meta.id)
    return new.to_dict()


@registry.method("pane.rename", "Rename a pane", "pane, name")
async def pane_rename(ctx, p: dict) -> None:
    ctx.manager.get(_pane(ctx, p)).meta.name = need(p, "name")[:60]
    ctx.manager._changed()


@registry.method("pane.focus", "Mark a pane focused and read", "pane")
async def pane_focus(ctx, p: dict) -> None:
    ctx.manager.focus(_pane(ctx, p))


@registry.method("pane.list", "List panes with state", "")
async def pane_list(ctx, p: dict) -> list:
    return [pane.to_dict() for pane in ctx.manager.panes.values()]
