"""One running program (agent or shell) in a pseudo-terminal, plus its derived state."""

from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from drover.core.pane_screen_text import PaneScreen
from drover.core.parent_notes import DraftTracker
from drover.core.terminal_mode_tracker import TerminalModes
from drover.pty.pty_backend_factory import create_pty_backend
from drover.status.osc7501_parser import parse_osc7501
from drover.status.status_change_tracker import StatusTracker

REPLAY_LIMIT = 512 * 1024  # characters of raw output kept for re-attaching clients
SCREEN_FLUSH_DELAY = 0.15  # seconds; pyte is updated at most ~7x/s per pane


@dataclass
class PaneMeta:
    id: str
    name: str
    kind: str
    command: str
    argv: list[str]
    cwd: str
    space_id: str
    tab_id: str
    parent: str | None = None
    created_at: float = field(default_factory=time.time)
    resume: str = ""
    outlive_parent: bool = False  # keep running when the pane that started it exits


class PaneSession:
    def __init__(self, meta: PaneMeta, cols: int, rows: int, history: int) -> None:
        self.meta = meta
        self.cols, self.rows = cols, rows
        self.screen = PaneScreen(cols, rows, history)
        self.tracker = StatusTracker()
        self.modes = TerminalModes()
        self.read_lock = asyncio.Lock()  # serialises viewport-scrolling reads
        self.input_lock = asyncio.Lock()  # keeps one prompt's paste and Enter together
        self.detection_paused_until = 0.0  # after a scrolling read, until its redraws age out
        self.replay: deque[str] = deque()
        self._replay_size = 0
        self.last_output_at = 0.0
        self.screen_changed_at = 0.0  # last output that changed visible text (not just terminal modes)
        self.dirty = False
        self.unread = False
        self.exit_code: int | None = None
        self.focused = False
        self.draft = DraftTracker()  # what the person typed here since their last Enter (guards parent notes)
        self.backend = None
        self.output_listeners: set[Callable[[str, str], None]] = set()
        self._pending_screen: list[str] = []
        self._screen_flush_scheduled = False
        self.on_exit_hook: Callable[[PaneSession], None] | None = None
        self.shell_launched = False  # started as a shell: its kind follows the foreground program
        self.fg_pgid: int | None = None
        self.fg_checked_at = 0.0
        self.claude_checked_at = 0.0

    # -- lifecycle -----------------------------------------------------------------
    def start(self, argv: list[str], env: dict[str, str]) -> None:
        self.backend = create_pty_backend(self._on_output, self._on_exit)
        self.backend.spawn(argv, self.meta.cwd, env, self.cols, self.rows)

    def _on_output(self, data: str) -> None:
        # Hot path: hand bytes to viewers first so typing feels instant.
        for listener in list(self.output_listeners):
            listener(self.meta.id, data)
        self.last_output_at = time.time()
        self.replay.append(data)
        self._replay_size += len(data)
        while self._replay_size > REPLAY_LIMIT and len(self.replay) > 1:
            self._replay_size -= len(self.replay.popleft())
        self.modes.feed(data)
        report = parse_osc7501(data) if "\x1b]7501;" in data else None
        if report:
            self.tracker.report(report["state"])
        # pyte (pure Python, slow) only feeds detection/read/search: batch it off the hot path.
        self._pending_screen.append(data)
        if not self._screen_flush_scheduled:
            self._screen_flush_scheduled = True
            asyncio.get_running_loop().call_later(SCREEN_FLUSH_DELAY, self.flush_screen)

    def flush_screen(self) -> None:
        self._screen_flush_scheduled = False
        if self._pending_screen:
            chunk = "".join(self._pending_screen)
            self._pending_screen.clear()
            if self.screen.feed(chunk):
                self.screen_changed_at = time.time()
            self.dirty = True

    def _on_exit(self, code: int | None) -> None:
        self.exit_code = code
        self.tracker.mark_exited()
        if self.on_exit_hook:
            self.on_exit_hook(self)

    # -- io ------------------------------------------------------------------------
    def write(self, data: str) -> None:
        if self.backend:
            self.backend.write(data)

    def resize(self, cols: int, rows: int) -> bool:
        """True when the size changed (viewers need a `state` event to learn it)."""
        cols, rows = max(10, min(cols, 500)), max(3, min(rows, 300))
        if (cols, rows) == (self.cols, self.rows):
            return False
        self.cols, self.rows = cols, rows
        self.screen.resize(cols, rows)
        if self.backend:
            self.backend.resize(cols, rows)
        return True

    def kill(self, wait: bool = False) -> None:
        """Terminate the process. Off the event loop by default (ConPTY teardown takes 100+ ms); `wait` for shutdown."""
        if not self.backend:
            return
        if wait:
            self.backend.kill()
        else:
            threading.Thread(target=self.backend.kill, name=f"kill-{self.meta.id}", daemon=True).start()

    def replay_text(self) -> str:
        return "".join(self.replay)

    @property
    def alive(self) -> bool:
        return bool(self.backend and self.backend.is_alive())

    @property
    def state(self) -> str:
        return self.tracker.state

    def to_dict(self) -> dict[str, Any]:
        m = self.meta
        return {
            "id": m.id, "name": m.name, "kind": m.kind, "command": m.command, "cwd": m.cwd,
            "space_id": m.space_id, "tab_id": m.tab_id, "parent": m.parent,
            "created_at": m.created_at, "state": self.state, "since": self.tracker.since,
            "unread": self.unread, "exit_code": self.exit_code, "title": self.screen.title,
            "machine": "local", "cols": self.cols, "rows": self.rows,
        }
