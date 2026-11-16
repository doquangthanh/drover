"""A pyte screen that also understands the alternate screen, for drawing one pane in the TUI.

pyte ignores `?47/?1047/?1049` (alternate screen), but Claude's fullscreen mode and OpenCode draw there.
Pure Python (no Textual), so it is easy to test. Fed with the daemon's `replay` + `out` websocket text.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import pyte

from drover.core.terminal_mode_tracker import ALT_SCREEN_MODES, TerminalModes

log = logging.getLogger(__name__)
_SWITCH_RE = re.compile(r"(\x1b\[\?(?:[\d;]*)[hl])")
_MODE_RE = re.compile(r"\x1b\[\?([\d;]+)([hl])")


@dataclass(frozen=True)
class CellStyle:
    fg: str = "default"
    bg: str = "default"
    bold: bool = False
    italics: bool = False
    underscore: bool = False
    strikethrough: bool = False
    reverse: bool = False


SCROLLBACK_LINES = 5000


class TerminalEmulatorScreen:
    def __init__(self, cols: int, rows: int) -> None:
        self.modes = TerminalModes()
        self.app_cursor = False  # DECCKM: arrows are sent as \x1bOA instead of \x1b[A
        self._main = pyte.HistoryScreen(cols, rows, history=SCROLLBACK_LINES, ratio=0.5)
        self.scroll = 0  # lines scrolled back into the main screen's history (0 = live view)
        self._alt = pyte.Screen(cols, rows)
        self._streams = {id(s): pyte.Stream(s) for s in (self._main, self._alt)}
        self._active = self._main
        self.version = 0  # bumps on every change; the widget redraws when it moved

    @property
    def cols(self) -> int:
        return self._active.columns

    @property
    def rows(self) -> int:
        return self._active.lines

    @property
    def cursor(self) -> tuple[int, int]:
        return self._active.cursor.x, self._active.cursor.y

    @property
    def cursor_hidden(self) -> bool:
        return self._active.cursor.hidden or self.scroll > 0

    @property
    def alt_screen(self) -> bool:
        return self._active is self._alt

    @property
    def history_size(self) -> int:
        return len(self._main.history.top)

    def scroll_by(self, lines: int) -> None:
        """Positive = back in time. The alternate screen (vim, less...) has no history of its own."""
        limit = 0 if self.alt_screen else self.history_size
        new = max(0, min(limit, self.scroll + lines))
        if new != self.scroll:
            self.scroll = new
            self.version += 1

    def scroll_to_bottom(self) -> None:
        self.scroll_by(-self.scroll)

    def _line(self, y: int):
        """Row y of what is on view: history lines while scrolled back, then the live screen."""
        if self.scroll <= 0 or self.alt_screen:
            return self._active.buffer[y]
        top = self._main.history.top
        index = len(top) - self.scroll + y
        return top[index] if index < len(top) else self._main.buffer[index - len(top)]

    def visible_text(self) -> str:
        return "\n".join("".join(t for t, _ in self.row_runs(y)).rstrip() for y in range(self.rows))

    def resize(self, cols: int, rows: int) -> None:
        if (cols, rows) == (self.cols, self.rows):
            return
        for screen in (self._main, self._alt):
            screen.resize(rows, cols)
        self.version += 1

    def feed(self, data: str) -> None:
        self.modes.feed(data)
        # Split so each pyte stream only sees text meant for its own screen.
        for part in _SWITCH_RE.split(data) if "\x1b[?" in data else [data]:
            if part.startswith("\x1b[?"):
                self._mode_sequence(part)
            else:
                self._feed_active(part)
        self.version += 1

    def _feed_active(self, text: str) -> None:
        if not text:
            return
        try:
            self._streams[id(self._active)].feed(text)
        except Exception as exc:  # noqa: BLE001 - pyte can trip over unusual sequences; never kill the view
            log.debug("pyte feed error: %s", exc)

    def _mode_sequence(self, seq: str) -> None:
        match = _MODE_RE.fullmatch(seq)
        if not match:
            return
        on = match.group(2) == "h"
        for mode in match.group(1).split(";"):
            if mode in ALT_SCREEN_MODES:
                self._switch(alt=on)
            elif mode == "1":
                self.app_cursor = on
        self._feed_active(seq)  # pyte still handles cursor visibility (?25) and the rest

    def _switch(self, alt: bool) -> None:
        target = self._alt if alt else self._main
        if target is self._active:
            return
        if alt:
            self._alt.reset()
        self._active = target

    def row_runs(self, y: int) -> list[tuple[str, CellStyle]]:
        """One row as (text, style) runs; neighbouring cells with the same style are merged."""
        screen = self._active
        row = self._line(y)
        runs: list[tuple[str, CellStyle]] = []
        for x in range(screen.columns):
            ch = row[x]
            style = CellStyle(ch.fg, ch.bg, ch.bold, ch.italics, ch.underscore, ch.strikethrough, ch.reverse)
            text = ch.data  # "" is the second half of a wide character
            if runs and runs[-1][1] == style:
                runs[-1] = (runs[-1][0] + text, style)
            else:
                runs.append((text, style))
        return runs
