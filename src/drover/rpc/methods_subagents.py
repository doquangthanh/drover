"""RPC for Claude Code sub-agents (Task/Agent tool) reported by `dr hook claude`: one virtual lane per sub-agent."""

from __future__ import annotations

from drover.rpc.rpc_registry import E_BAD_PARAMS, E_NOT_FOUND, RpcError, need, registry


def virtual_id(pane_id: str, agent_id: str) -> str:
    """Sub-agent id on the Flow board: `<pane>/<agent>`; AgentMessagesLog.for_tree keeps it with its pane's tree."""
    return f"{pane_id}/{agent_id}"


@registry.method("agent.subagent", "A Claude Code sub-agent started or stopped inside a pane", "pane, event, id, name?, text?")
async def agent_subagent(ctx, p: dict) -> None:
    pane_id, event, agent_id = need(p, "pane"), need(p, "event"), need(p, "id")
    if pane_id not in ctx.manager.panes:
        raise RpcError(E_NOT_FOUND, f"no pane {pane_id}")
    if event not in ("start", "stop") or "/" in agent_id:
        raise RpcError(E_BAD_PARAMS, "event must be start or stop; id has no '/'")
    sub = virtual_id(pane_id, agent_id)
    if event == "start":
        message = ctx.manager.messages.add("sub-start", pane_id, sub, str(p.get("name") or "agent"))
    else:
        message = ctx.manager.messages.add("sub-done", sub, pane_id, str(p.get("text") or ""))
    # Sub-agents don't change any pane's state, so tell the UI to refetch the tree's messages.
    ctx.hub.emit("messages", message.to_dict())
