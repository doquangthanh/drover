"""Herdr-style tab bar: padded tab blocks, the open one in the accent colour, `+`, and the hint at the right edge."""

from drover.tui.tab_bar import TAB_OFF, tab_bar_text
from drover.tui.tui_state_helpers import ACCENT_CHIP

STATE = {
    "spaces": [{"id": "s1", "name": "api"}],
    "tabs": [{"id": "t1", "space_id": "s1", "name": "claude-2", "layout": {"pane": "%1"}},
             {"id": "t2", "space_id": "s1", "name": "logs", "layout": {"pane": "%2"}}],
    "panes": [{"id": "%1", "state": "blocked"}, {"id": "%2", "state": "idle"}],
    "stopped": [],
}


def _styles_at(text, start, end) -> set[str]:
    return {str(s.style) for s in text.spans if s.start < end and s.end > start}


def test_tabs_are_blocks_with_the_open_one_in_the_accent():
    text, spans = tab_bar_text(STATE, "s1", "t2", "Ctrl+B", width=60)
    (s1, e1, t1), (s2, e2, t2), (sp, ep, plus) = spans
    assert (t1, t2, plus) == ("t1", "t2", "+")
    assert text.plain[s1:e1].strip() == "1 ! claude-2"  # a tab that needs you shows its state glyph
    assert text.plain[s2:e2].strip() == "2 logs"  # an idle tab does not
    assert ACCENT_CHIP in _styles_at(text, s2, e2) and TAB_OFF in _styles_at(text, s1, e1)
    assert text.plain[sp:ep] == " + "


def test_hint_sits_at_the_right_edge_and_a_narrow_bar_drops_it():
    text, _ = tab_bar_text(STATE, "s1", "t1", "Ctrl+B", width=60)
    assert text.cell_len == 60 and text.plain.endswith("Ctrl+B ? keys")
    narrow, _ = tab_bar_text(STATE, "s1", "t1", "Ctrl+B", width=20)
    assert narrow.cell_len <= 20 and "keys" not in narrow.plain
