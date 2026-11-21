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
from drover.tui.terminal_mouse_report_bytes import WHEEL_DOWN, WHEEL_UP, button_code, mouse_report
from drover.tui.textual_key_to_bytes import key_to_bytes

FRAME_SECONDS = 1 / 30  # redraw cap
WHEEL_LINES = 3
# Copy mode (Herdr prefix+[): move through the history; y copies what is on view, q / Esc leaves.
SCROLL_KEYS = {"up": 1, "k": 1, "down": -1, "j": -1, "pageup": "page", "ctrl+b": "page", "pagedown": "-page",
               "ctrl+f": "-page", "ctrl+u": "half", "ctrl+d": "-half", "g": "top", "home": "top",
               "G": "bottom", "end": "bottom"}
RESIZE_DEBOUNCE = 0.15
PLAIN = Style()  # never None: Textual filters (e.g. monochrome) read .color off every segment style


def rich_color(name: str) -> str | None:
    """pyte colour name -> Rich colour. Named colours stay ANSI so the terminal's own palette is used."""
    if name == "default":
        return None
    if name.startswith("bright"):
        base = name[6:]
        return "bright_" + ("yellow" if base == "brown" else base)  # pyte says "brown" for ANSI yellow
    if name == "brown":
        return "yellow"
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
        self.scroll_mode = False
        self.on_scroll_mode: Callable[[], None] = lambda: None  # the app redraws its status line

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
            return Strip.blank(self.size.width, PLAIN)
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
            segments.append(Segment(" " * (cx - x), PLAIN))
            segments.append(Segment(" ", rich_style(CellStyle(), cursor=True)))
        return Strip(segments).adjust_cell_length(self.size.width, PLAIN)

    def on_resize(self, event: events.Resize) -> None:
        cols, rows = self.size.width, self.size.height  # content box: the event size includes the border
        if cols < 2 or rows < 1:
            return
        self.emulator.resize(cols, rows)
        if self._resize_timer:
            self._resize_timer.stop()
        self._resize_timer = self.set_timer(RESIZE_DEBOUNCE, lambda: self._on_size(cols, rows))

    def set_scroll_mode(self, on: bool) -> None:
        self.scroll_mode = on
        if not on:
            self.emulator.scroll_to_bottom()
        self.on_scroll_mode()

    def _scroll_key(self, key: str, character: str | None) -> None:
        name = character if character in ("g", "G", "j", "k", "q", "y") else key
        if name in ("q", "escape"):
            return self.set_scroll_mode(False)
        if name == "y":
            self.app.copy_to_clipboard(self.emulator.visible_text())
            self.app.notify("Copied the visible lines")
            return self.set_scroll_mode(False)
        step = SCROLL_KEYS.get(name)
        rows = self.emulator.rows
        lines = {"page": rows, "-page": -rows, "half": rows // 2, "-half": -(rows // 2),
                 "top": self.emulator.history_size, "bottom": -self.emulator.scroll}.get(step, step)
        if isinstance(lines, int):
            self.emulator.scroll_by(lines)
            self.on_scroll_mode()

    def on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()  # Tab, Ctrl+C... belong to the agent, not to Textual's focus and copy bindings
        if self.scroll_mode:
            return self._scroll_key(event.key, event.character)
        data = key_to_bytes(event.key, event.character, self.emulator.app_cursor)
        if data:
            self.emulator.scroll_to_bottom()  # typing jumps back to the live screen
            self._on_input(data)

    def _report_mouse(self, event: events.MouseEvent, code: int | None, pressed: bool) -> bool:
        """Send the click/wheel to the app when it turned mouse reporting on (Claude's "Jump to bottom"...)."""
        modes = self.emulator.modes
        captured = self.app.mouse_captured is self
        offset = event.get_content_offset_capture(self) if captured else event.get_content_offset(self)
        if not modes.mouse or code is None or offset is None or self.scroll_mode:
            return False
        x = max(0, min(offset.x, self.emulator.cols - 1))  # a captured release may land outside the pane
        y = max(0, min(offset.y, self.emulator.rows - 1))
        report = mouse_report(code, x, y, pressed, modes.mouse_sgr)
        if report:
            self.emulator.scroll_to_bottom()  # the app's cells are the live screen, not our scrollback
            self._on_input(report)
        return True

    def on_mouse_down(self, event: events.MouseDown) -> None:
        code = button_code(event.button, event.shift, event.meta, event.ctrl)
        if self._report_mouse(event, code, pressed=True):
            self.capture_mouse()  # the release then comes back here even over another pane: no stuck button
            event.stop()

    def on_mouse_up(self, event: events.MouseUp) -> None:
        code = button_code(event.button, event.shift, event.meta, event.ctrl)
        forwarded = self._report_mouse(event, code, pressed=False)
        if self.app.mouse_captured is self:
            self.release_mouse()
        if forwarded:
            event.stop()

    def _wheel(self, lines: int) -> None:
        if self.emulator.alt_screen:  # full-screen apps scroll themselves: send arrows (xterm "alternate scroll")
            self._on_input(("\x1bOA" if self.emulator.app_cursor else "\x1b[A") * WHEEL_LINES if lines > 0
                           else ("\x1bOB" if self.emulator.app_cursor else "\x1b[B") * WHEEL_LINES)
            return
        self.emulator.scroll_by(lines)
        self.on_scroll_mode()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        event.stop()
        if not self._report_mouse(event, WHEEL_UP, pressed=True):
            self._wheel(WHEEL_LINES)

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        event.stop()
        if not self._report_mouse(event, WHEEL_DOWN, pressed=True):
            self._wheel(-WHEEL_LINES)

    def on_paste(self, event: events.Paste) -> None:
        text = event.text
        if self.emulator.modes.bracketed_paste:
            text = f"\x1b[200~{text}\x1b[201~"
        self._on_input(text)
        event.stop()
