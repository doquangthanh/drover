"""Tabs of the current space in one line above the panes, Herdr-style: each tab is a padded block (the open one in
the accent colour), a `+` to add one, and the key hint pushed to the right edge. Click a tab to open it."""

from __future__ import annotations

from rich.cells import cell_len
from rich.text import Text
from textual import events
from textual.message import Message
from textual.widgets import Static

from drover.tui.tui_state_helpers import ACCENT_CHIP, state_glyph, tab_state, tabs_of

TAB_OFF = "#8b919c on #2a2f38"  # tabs you are not on (Herdr: overlay text on a surface block)
MIN_TAB = 8
NEW_TAB = " + "


class TabClicked(Message):
    def __init__(self, tab_id: str) -> None:
        super().__init__()
        self.tab_id = tab_id


class NewTabClicked(Message):
    pass


def tab_bar_text(state: dict, space_id: str | None, tab_id: str | None, prefix: str,
                 width: int | None = None) -> tuple[Text, list[tuple[int, int, str]]]:
    """The bar's text and the cell span of each tab (and of `+`, id "+"), for clicks."""
    text, spans = Text(no_wrap=True), []
    for i, tab in enumerate(tabs_of(state, space_id) if space_id else [], start=1):
        on = tab["id"] == tab_id
        state_name = tab_state(state, tab)
        glyph, glyph_style = state_glyph(state_name)
        chip = ACCENT_CHIP if on else TAB_OFF
        label = Text(f"{i} ", "dim" if not on else "")  # the number is what Ctrl+B <n> jumps to
        if state_name != "idle":  # an idle tab needs nothing from you: no glyph, a quieter bar
            label.append(glyph + " ", chip if on else glyph_style)
        label.append(tab["name"])
        pad = max(MIN_TAB - label.cell_len, 4)
        start = text.cell_len
        text.append(" " * (pad // 2), chip)
        label.stylize_before(chip)  # the block underneath; the glyph keeps its own colour on top
        text.append_text(label)
        text.append(" " * (pad - pad // 2), chip)
        spans.append((start, text.cell_len, tab["id"]))
        text.append(" ")
    spans.append((text.cell_len, text.cell_len + len(NEW_TAB), "+"))
    text.append(NEW_TAB, "bold")
    hint = f"{prefix} ? keys"
    if width and text.cell_len + 2 + cell_len(hint) <= width:
        text.append(" " * (width - text.cell_len - cell_len(hint)))
        text.append(hint, "dim")
    elif width:
        text.truncate(width, overflow="ellipsis")
    return text, spans


class TabBar(Static):
    DEFAULT_CSS = "TabBar { height: 1; padding: 0 1; background: $panel; }"

    def __init__(self, **kwargs) -> None:
        super().__init__("", **kwargs)
        self._spans: list[tuple[int, int, str]] = []  # (start, end, tab id) in cells, for clicks
        self._last: tuple | None = None
        self.plain = ""

    def show(self, state: dict, space_id: str | None, tab_id: str | None, prefix: str) -> None:
        self._last = (state, space_id, tab_id, prefix)
        text, self._spans = tab_bar_text(state, space_id, tab_id, prefix, self.content_region.width or None)
        self.plain = text.plain
        self.update(text)

    def on_resize(self) -> None:
        if self._last:
            self.show(*self._last)  # the hint sits at the right edge, so a new width moves it

    def on_click(self, event: events.Click) -> None:
        x = event.x - 1  # the bar's left padding
        hit = next((tid for start, end, tid in self._spans if start <= x < end), None)
        if hit == "+":
            self.post_message(NewTabClicked())
        elif hit:
            self.post_message(TabClicked(hit))
