"""Track the DEC private modes an agent turns on: alternate screen, mouse reporting, bracketed paste.

pyte ignores these, but `dr prompt` (bracketed paste) and `dr read` (alternate-screen history) need them.
Only output containing "\\x1b[?" is scanned, so the hot path stays cheap.
"""

from __future__ import annotations

import re

_MODE_RE = re.compile(r"\x1b\[\?([\d;]+)([hl])")
ALT_SCREEN_MODES = {"47", "1047", "1049"}
MOUSE_MODES = {"1000", "1002", "1003"}


class TerminalModes:
    def __init__(self) -> None:
        self.alt_screen = False
        self.mouse = False  # any mouse-button reporting mode
        self.mouse_sgr = False  # SGR (1006) encoding: "\x1b[<b;x;yM"
        self.bracketed_paste = False

    def feed(self, data: str) -> None:
        if "\x1b[?" not in data:
            return
        for numbers, flag in _MODE_RE.findall(data):
            on = flag == "h"
            for mode in numbers.split(";"):
                if mode in ALT_SCREEN_MODES:
                    self.alt_screen = on
                elif mode in MOUSE_MODES:
                    self.mouse = on
                elif mode == "1006":
                    self.mouse_sgr = on
                elif mode == "2004":
                    self.bracketed_paste = on

    @property
    def scrollable_transcript(self) -> bool:
        """A full-screen app that scrolls its own history on mouse-wheel input (SGR encoded)."""
        return self.alt_screen and self.mouse and self.mouse_sgr
