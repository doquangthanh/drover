from drover.tui.responsive_mode import mode_for
from drover.tui.restore_logic import unasked_stopped
from drover.tui.tui_state_helpers import (
    default_tab_id,
    next_blocked_pane,
    panes_of,
    state_glyph,
    tab_of_pane,
    worst_state,
)

STATE = {
    "tabs": [{"id": "t1", "space_id": "s1", "name": "a", "focused": "%1",
              "layout": {"split": "row", "ratio": 0.5, "a": {"pane": "%1"}, "b": {"pane": "%2"}}},
             {"id": "t2", "space_id": "s1", "name": "b", "focused": "%3", "layout": {"pane": "%3"}}],
    "panes": [{"id": "%1", "state": "working", "unread": False}, {"id": "%2", "state": "blocked", "unread": True},
              {"id": "%3", "state": "idle", "unread": False}],
    "stopped": [{"id": "%9", "name": "old", "tab_id": "t1"}],
}


def test_worst_state_priority():
    assert worst_state(["idle", "working", "blocked"]) == "blocked"
    assert worst_state(["idle", "done", "working"]) == "done"
    assert worst_state(["exited", "stopped"]) == "exited"
    assert worst_state([]) == "idle"


def test_glyphs():
    assert state_glyph("working")[0] == "●" and state_glyph("blocked")[0] == "!"
    assert state_glyph("done")[0] == "✓" and state_glyph("stopped")[0] == "×"
    assert state_glyph("nonsense") == state_glyph("idle")


def test_panes_of_follows_layout_and_marks_stopped():
    assert [p["id"] for p in panes_of(STATE, STATE["tabs"][0])] == ["%1", "%2"]
    stopped_tab = {"layout": {"pane": "%9"}}
    assert panes_of(STATE, stopped_tab)[0]["state"] == "stopped"


def test_tab_of_pane_and_default_tab():
    assert tab_of_pane(STATE, "%3")["id"] == "t2"
    assert tab_of_pane(STATE, "%404") is None
    assert default_tab_id(STATE) == "t2"
    assert default_tab_id({"tabs": [], "panes": []}) is None


def test_next_blocked_cycles():
    assert next_blocked_pane(STATE, None) == "%2"
    assert next_blocked_pane({"panes": []}, None) is None


def test_unasked_stopped_skips_asked_and_remote():
    stopped = [{"id": "%1"}, {"id": "%2"}, {"id": "box:%3"}]
    assert [s["id"] for s in unasked_stopped(stopped, {"%1"})] == ["%2"]


def test_mode_for_breakpoints():
    assert mode_for(120, 40) == "wide" and mode_for(100, 30) == "wide"
    assert mode_for(99, 30) == "medium" and mode_for(60, 15) == "medium"
    assert mode_for(59, 30) == "narrow" and mode_for(120, 14) == "narrow"
