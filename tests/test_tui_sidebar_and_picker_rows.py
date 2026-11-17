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


LONG = {
    "spaces": [{"id": "s1", "name": "tenant-centralization-verification", "branch": "saas/feature/CV-187-base",
                "ahead": 2, "dirty": 3},
               {"id": "s2", "name": "eCamOpsService", "branch": "main", "ahead": 0, "dirty": 0},
               {"id": "s3", "name": "notes"}],
    "tabs": [{"id": "t1", "space_id": "s1", "name": "review", "layout": {"split": "row", "ratio": 0.5,
                                                                          "a": {"pane": "%1"}, "b": {"pane": "%2"}}},
             {"id": "t2", "space_id": "s2", "name": "codex-a-very-long-agent-name", "layout": {"pane": "%3"}}],
    "panes": [{"id": "%1", "name": "claude", "kind": "claude", "state": "working"},
              {"id": "%2", "name": "claude-10", "kind": "claude", "state": "idle"},
              {"id": "%3", "name": "codex-a-very-long-agent-name", "kind": "codex", "state": "done"}],
    "stopped": [],
}


def _lines(rows) -> dict[str, list[str]]:
    return {oid: label.plain.split("\n") for oid, label in rows}


def test_spaces_show_branch_and_git_counts_on_a_second_line():
    rows = _lines(space_rows(LONG, None))
    assert rows["s1"] == ["● tenant-centralization-verification", "  saas/feature/CV-187-base · ↑2 · ±3"]
    assert rows["s2"] == ["✓ eCamOpsService", "  main"]  # zero counts leave no separator behind
    assert rows["s3"] == ["○ notes"]  # not a git repo: one line


def test_agents_show_where_then_the_agent_name():
    rows = _lines(agent_rows(LONG))
    assert rows["%1"] == ["● tenant-centralization-verification · review", "  claude"]
    assert rows["%3"] == ["✓ eCamOpsService", "  codex-a-very-long-agent-name"]  # tab named after the pane: once


def test_every_line_fits_the_width_and_ends_in_an_ellipsis():
    for _, label in space_rows(LONG, None, width=20) + agent_rows(LONG, width=20):
        assert all(len(line) <= 20 for line in label.plain.split("\n")), label.plain
    assert _lines(space_rows(LONG, None, width=20))["s1"][0].endswith("…")


def test_pane_title_colours_the_glyph_and_escapes_the_name():
    from textual.content import Content

    from drover.tui.split_layout_view import pane_title

    title = Content.from_markup(pane_title("blocked", "fix [bug] now"))
    assert title.plain == "! fix [bug] now"  # a name with brackets is not read as markup
    assert pane_title("working", "a").startswith("[#76a8ff]●[/]")
