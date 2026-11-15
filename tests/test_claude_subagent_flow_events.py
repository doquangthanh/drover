"""Claude Code sub-agents on the Flow board: hook payload mapping, agent.subagent RPC, tree filter, claude argv."""

import asyncio
from types import SimpleNamespace

import pytest

from drover.cli.cli_hook_claude import payload_to_params
from drover.core import claude_subagent_hooks as hooks
from drover.core.agent_messages_log import AgentMessagesLog
from drover.rpc.methods_subagents import agent_subagent
from drover.rpc.rpc_registry import RpcError

# Trimmed from real Claude Code 2.1 hook payloads.
START = {"hook_event_name": "SubagentStart", "agent_id": "a96f", "agent_type": "general-purpose", "session_id": "s"}
STOP = {"hook_event_name": "SubagentStop", "agent_id": "a96f", "agent_type": "general-purpose",
        "last_assistant_message": "hi\n  there"}


def test_payload_mapping():
    assert payload_to_params(START, "%7") == {"pane": "%7", "event": "start", "id": "a96f",
                                              "name": "general-purpose", "text": ""}
    assert payload_to_params(STOP, "%7")["text"] == "hi there"
    long = payload_to_params({**STOP, "last_assistant_message": "x" * 500}, "%7")["text"]
    assert len(long) == 201 and long.endswith("…")


@pytest.mark.parametrize("payload, pane", [
    ({"hook_event_name": "PreToolUse", "agent_id": "a"}, "%7"),  # not a sub-agent event
    ({"hook_event_name": "SubagentStart"}, "%7"),  # no agent id
    (START, ""),  # not inside a drover pane
])
def test_payloads_we_ignore(payload, pane):
    assert payload_to_params(payload, pane) is None


class FakeHub:
    def __init__(self):
        self.events = []

    def emit(self, name, data):
        self.events.append((name, data))


def make_ctx():
    manager = SimpleNamespace(panes={"%7": object()}, messages=AgentMessagesLog())
    return SimpleNamespace(manager=manager, hub=FakeHub())


def test_rpc_logs_start_and_stop_on_a_virtual_lane():
    ctx = make_ctx()
    asyncio.run(agent_subagent(ctx, {"pane": "%7", "event": "start", "id": "a96f", "name": "planner"}))
    asyncio.run(agent_subagent(ctx, {"pane": "%7", "event": "stop", "id": "a96f", "text": "plan ready"}))
    got = [(m.kind, m.source, m.target, m.text) for m in ctx.manager.messages.items]
    assert got == [("sub-start", "%7", "%7/a96f", "planner"), ("sub-done", "%7/a96f", "%7", "plan ready")]
    assert [name for name, _ in ctx.hub.events] == ["messages", "messages"]


@pytest.mark.parametrize("params", [
    {"pane": "%9", "event": "start", "id": "a"},  # unknown pane
    {"pane": "%7", "event": "boom", "id": "a"},
    {"pane": "%7", "event": "start", "id": "x/y"},
])
def test_rpc_rejects_bad_params(params):
    with pytest.raises(RpcError):
        asyncio.run(agent_subagent(make_ctx(), params))


def test_for_tree_keeps_sub_agents_of_its_panes():
    log = AgentMessagesLog()
    log.add("sub-start", "%7", "%7/a")
    log.add("sub-start", "%8", "%8/b")
    log.add("sub-done", "%7/a", "%7")
    assert [m["target"] for m in log.for_tree({"%7"})] == ["%7/a", "%7"]


def test_claude_argv_gets_settings_file(tmp_path, monkeypatch):
    monkeypatch.setattr(hooks, "state_dir", lambda: tmp_path)
    argv = hooks.with_subagent_hooks(["claude", "--continue"])
    assert argv[:2] == ["claude", "--settings"] and argv[3:] == ["--continue"]
    body = (tmp_path / "claude-subagent-hooks.json").read_text(encoding="utf-8")
    assert "SubagentStart" in body and "SubagentStop" in body and "hook claude" in body
    assert hooks.with_subagent_hooks(["codex"]) == ["codex"]
    assert hooks.with_subagent_hooks(["claude", "--settings", "mine.json"]) == ["claude", "--settings", "mine.json"]
    assert hooks.with_subagent_hooks([r"C:\npm\claude.cmd"])[1] == "--settings"
