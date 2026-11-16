"""Textual widget that draws one pane: the daemon's raw output goes through a pyte screen, keys go back as bytes."""

from __future__ import annotations

from collections.abc import Callable

from rich.segment import Segment
from rich.style import Style
from textual import events
from textual.strip import Strip
from textual.timer import Timer
from textual.widget import Widget

from drover.tui.terminal_emulator_screen import CellStyle, TerminalEmulatorScreen
from drover.tui.textual_key_to_bytes import key_to_bytes

FRAME_SECONDS = 1 / 30  # redraw cap
RESIZE_DEBOUNCE = 0.15


def rich_color(name: str) -> str | None:
    """pyte colour name -> Rich colour. Named colours stay ANSI so the terminal's own palette is used."""
    if name == "default":
        return None
    if name == "brown":  # pyte's word for ANSI yellow
        return "yellow"
    if name.startswith("bright"):
        return "bright_" + name[6:]
    if len(name) == 6 and all(c in "0123456789abcdef" for c in name):
        return "#" + name
    return name


def rich_style(cell: CellStyle, cursor: bool = False) -> Style:
    return Style(color=rich_color(cell.fg), bgcolor=rich_color(cell.bg), bold=cell.bold, italic=cell.italics,
                 underline=cell.underscore, strike=cell.strikethrough, reverse=cell.reverse != cursor)


class TerminalPaneView(Widget, can_focus=True):
    DEFAULT_CSS = "TerminalPaneView { width: 1fr; height: 1fr; }"

    def __init__(self, on_input: Callable[[str], None], on_size: Callable[[int, int], None], **kwargs) -> None:
        super().__init__(**kwargs)
        self.emulator = TerminalEmulatorScreen(80, 24)
        self._on_input = on_input
        self._on_size = on_size
        self._drawn = -1
        self._resize_timer: Timer | None = None

    def on_mount(self) -> None:
        self.set_interval(FRAME_SECONDS, self._tick)

    def feed(self, data: str, replay: bool = False) -> None:
        if replay:  # the daemon sends a full replay on every (re)attach: start from a clean screen
            self.emulator = TerminalEmulatorScreen(self.emulator.cols, self.emulator.rows)
            self._drawn = -1
        self.emulator.feed(data)

    def _tick(self) -> None:
        if self.emulator.version != self._drawn:
            self._drawn = self.emulator.version
            self.refresh()

    def render_line(self, y: int) -> Strip:
        em = self.emulator
        if y >= em.rows:
            return Strip.blank(self.size.width)
        cx, cy = em.cursor
        show_cursor = self.has_focus and not em.cursor_hidden and y == cy
        segments: list[Segment] = []
        x = 0
        for text, cell in em.row_runs(y):
            width = len(text)  # "" cells (wide-char tails) add nothing, so len == cells only for narrow text
            if show_cursor and x <= cx < x + width:
                before, here, after = text[: cx - x], text[cx - x], text[cx - x + 1:]
                for part, cur in ((before, False), (here, True), (after, False)):
                    if part:
                        segments.append(Segment(part, rich_style(cell, cursor=cur)))
            elif text:
                segments.append(Segment(text, rich_style(cell)))
            x += width
        if show_cursor and cx >= x:  # cursor past the last drawn text
            segments.append(Segment(" " * (cx - x), None))
            segments.append(Segment(" ", rich_style(CellStyle(), cursor=True)))
        return Strip(segments).adjust_cell_length(self.size.width)

    def on_resize(self, event: events.Resize) -> None:
        cols, rows = self.size.width, self.size.height  # content box: the event size includes the border
        if cols < 2 or rows < 1:
            return
        self.emulator.resize(cols, rows)
        if self._resize_timer:
            self._resize_timer.stop()
        self._resize_timer = self.set_timer(RESIZE_DEBOUNCE, lambda: self._on_size(cols, rows))

    def on_key(self, event: events.Key) -> None:
        data = key_to_bytes(event.key, event.character, self.emulator.app_cursor)
        event.stop()
        event.prevent_default()  # Tab, Ctrl+C... belong to the agent, not to Textual's focus and copy bindings
        if data:
            self._on_input(data)

    def on_paste(self, event: events.Paste) -> None:
        text = event.text
        if self.emulator.modes.bracketed_paste:
            text = f"\x1b[200~{text}\x1b[201~"
        self._on_input(text)
        event.stop()
