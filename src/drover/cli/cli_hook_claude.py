"""`dr hook claude`: Claude Code hook (SubagentStart / SubagentStop) -> sub-agent lane events on the Flow board.

Claude Code runs this itself (not the model), with the hook payload on stdin and the pane's env (DR_PANE_ID), for
claude panes drover started (see core/claude_subagent_hooks.py). It must never slow down or break Claude: it prints
nothing (hook stdout can reach Claude's context), times out fast, swallows every error and always exits 0.
"""

from __future__ import annotations

import json
import os
import sys

EVENTS = {"SubagentStart": "start", "SubagentStop": "stop"}
MAX_TEXT = 200


def add_hook_parser(sub) -> None:
    hook = sub.add_parser("hook", help="internal: Claude Code hook that reports sub-agents to the agent tree")
    hook.add_argument("agent", choices=["claude"])


def payload_to_params(payload: dict, pane: str) -> dict | None:
    """Map a hook payload to `agent.subagent` params; None for events and payloads we don't use."""
    event = EVENTS.get(payload.get("hook_event_name", ""))
    agent_id = payload.get("agent_id")
    if not event or not pane or not isinstance(agent_id, str) or not agent_id:
        return None
    text = str(payload.get("last_assistant_message") or "") if event == "stop" else ""
    text = " ".join(text.split())
    return {"pane": pane, "event": event, "id": agent_id, "name": str(payload.get("agent_type") or "agent"),
            "text": text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "…"}


def cmd_hook(args) -> int:
    try:
        stdin = sys.stdin.read() if sys.stdin else ""
        params = payload_to_params(json.loads(stdin or "{}"), os.environ.get("DR_PANE_ID", ""))
        if params:
            from drover.daemon import daemon_client as dc

            dc.call("agent.subagent", params, timeout=2, autostart=False)
    except Exception:  # noqa: BLE001, S110 - a hook must never fail Claude, and must print nothing
        pass
    return 0
