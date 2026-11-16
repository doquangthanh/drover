"""Tabs of the current space in one line above the panes (Herdr's tab surface). Click a tab to open it."""

from __future__ import annotations

from rich.text import Text
from textual import events
from textual.message import Message
from textual.widgets import Static

from drover.tui.tui_state_helpers import state_glyph, tab_state, tabs_of


class TabClicked(Message):
    def __init__(self, tab_id: str) -> None:
        super().__init__()
        self.tab_id = tab_id


class TabBar(Static):
    DEFAULT_CSS = "TabBar { height: 1; padding: 0 1; background: $panel; }"

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._spans: list[tuple[int, int, str]] = []  # (start, end, tab id) in cells, for clicks
        self.plain = ""

    def show(self, state: dict, space_id: str | None, tab_id: str | None, prefix: str) -> None:
        text, self._spans = Text(), []
        for i, tab in enumerate(tabs_of(state, space_id) if space_id else [], start=1):
            glyph, style = state_glyph(tab_state(state, tab))
            start = text.cell_len
            on = tab["id"] == tab_id
            text.append(f" {i} ", "bold reverse" if on else "dim")
            text.append(glyph, style)
            text.append(f" {tab['name']} ", "bold reverse" if on else "")
            self._spans.append((start + 1, text.cell_len + 1, tab["id"]))  # +1: the bar's left padding
            text.append(" ")
        text.append(f"  {prefix} c new tab · {prefix} ? keys", "dim")
        self.plain = text.plain
        self.update(text)

    def on_click(self, event: events.Click) -> None:
        hit = next((tid for start, end, tid in self._spans if start <= event.x < end), None)
        if hit:
            self.post_message(TabClicked(hit))
