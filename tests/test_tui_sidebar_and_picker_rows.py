"""Herdr-style sidebar and goto picker rows (pure functions over a state snapshot)."""

from drover.tui.goto_picker_dialog import picker_rows
from drover.tui.workspace_sidebar import agent_rows, space_rows

STATE = {
    "spaces": [{"id": "s1", "name": "api"}, {"id": "s2", "name": "web"}],
    "tabs": [{"id": "t1", "space_id": "s1", "name": "one", "layout": {"pane": "%1"}},
             {"id": "t2", "space_id": "s2", "name": "two", "layout": {"pane": "%2"}}],
    "panes": [{"id": "%1", "name": "shell", "kind": "shell", "state": "idle"},
              {"id": "%2", "name": "claude", "kind": "claude", "state": "blocked"}],
    "stopped": [],
}


def test_agents_hide_plain_shells():
    assert [pid for pid, _ in agent_rows(STATE)] == ["%2"]


def test_spaces_show_their_worst_state():
    rows = dict(space_rows(STATE, "s1"))
    assert rows["s2"].plain.startswith("!")  # blocked
    assert rows["s1"].plain.endswith("api")


def test_picker_lists_everything_blocked_first():
    assert [pid for pid, _, _ in picker_rows(STATE)] == ["%2", "%1"]
