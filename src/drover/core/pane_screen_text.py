"""Plain-text views of a pyte screen: visible lines, scrollback, search."""

from __future__ import annotations

import logging

import pyte

log = logging.getLogger(__name__)


class PaneScreen:
    """Server-side terminal model used for detection, `dr read` and search.

    The browser renders with xterm.js; this copy only needs to be good enough to read text.
    """

    def __init__(self, cols: int, rows: int, history: int) -> None:
        self.screen = pyte.HistoryScreen(cols, rows, history=history, ratio=0.5)
        self.stream = pyte.Stream(self.screen)

    def feed(self, data: str) -> bool:
        """Apply output. True when visible cells changed (mode switches and terminal queries do not count)."""
        self.screen.dirty.clear()
        try:
            self.stream.feed(data)
        except Exception as exc:  # pyte can trip over unusual sequences; never kill the pane
            log.debug("pyte feed error: %s", exc)
        return bool(self.screen.dirty)

    def resize(self, cols: int, rows: int) -> None:
        try:
            self.screen.resize(rows, cols)
        except Exception as exc:
            log.debug("pyte resize error: %s", exc)

    @property
    def title(self) -> str:
        return getattr(self.screen, "title", "") or ""

    def visible_lines(self) -> list[str]:
        return [line.rstrip() for line in self.screen.display]

    def history_lines(self) -> list[str]:
        out = []
        for row in self.screen.history.top:
            # History rows only hold written cells; walk up to the last one instead of the full width.
            width = max(row.keys(), default=-1) + 1
            out.append("".join(row[x].data for x in range(width)).rstrip())
        return out

    def all_lines(self) -> list[str]:
        lines = self.history_lines() + self.visible_lines()
        while lines and not lines[-1]:
            lines.pop()
        return lines

    def read_text(self, last: int | None = None) -> str:
        lines = self.all_lines()
        if last:
            lines = lines[-last:]
        return "\n".join(lines)

    def search(self, needle: str, limit: int = 20) -> list[tuple[int, str]]:
        needle_low = needle.lower()
        hits = []
        for number, line in enumerate(self.all_lines(), start=1):
            if needle_low in line.lower():
                hits.append((number, line.strip()[:200]))
                if len(hits) >= limit:
                    break
        return hits
