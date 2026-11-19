"""Notes a helper's parent gets when the helper finishes, needs an answer or exits (Herdr's parent notes).

The daemon types them into the parent agent, like a short message from the helper:

    <dr from="%7 review" state="done">finished; read it with: dr read review</dr>

Typed only when it is safe: the parent is a live agent (not a shell, which would run the text), it is not on a
permission prompt (the Enter would answer it), it is not inside a `dr wait` (that reply already carries the news)
and the person has no half-typed message in it.
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

NOTE_STATES = ("done", "blocked", "exited")
DRAFT_HOLD = 60.0  # a draft older than this is treated as abandoned, as in Herdr
_ESCAPES = re.compile(r"\x1b(\[[0-9;?]*[ -/]*[@-~]|O.|\][^\x07\x1b]*(\x07|\x1b\\)|.)")


@dataclass
class DraftTracker:
    """Whether the person has typed into a pane since their last Enter."""

    pending: bool = False
    key_at: float = 0.0

    def feed(self, data: str, now: float | None = None) -> None:
        now = now or time.time()
        text = _ESCAPES.sub("", data)  # arrows, focus reports, mouse: not typing
        if not text:
            return
        self.key_at = now
        parts = re.split(r"[\r\n\x03\x15]", text)  # after Enter, Ctrl+C or Ctrl+U the line starts empty
        if len(parts) > 1:
            self.pending = False
        if any(ch >= " " and ch != "\x7f" for ch in parts[-1]):
            self.pending = True

    def blocks(self, now: float) -> bool:
        return self.pending and now - self.key_at < DRAFT_HOLD


@dataclass
class _Note:
    child: str
    name: str
    state: str
    detail: str


@dataclass
class ParentNotes:
    queue: dict[str, list[_Note]] = field(default_factory=dict)
    waits: dict[str, int] = field(default_factory=dict)  # parent id -> active dr wait calls
    sending: set[str] = field(default_factory=set)

    def add(self, parent: str, child: str, name: str, state: str, detail: str = "") -> None:
        notes = [n for n in self.queue.get(parent, []) if n.child != child]  # only a helper's latest news counts
        self.queue[parent] = notes + [_Note(child, name, state, detail)]

    def drop(self, parent: str, children) -> None:
        """A `dr wait` reply already told the parent about these helpers."""
        gone = set(children)
        left = [n for n in self.queue.get(parent, []) if n.child not in gone]
        if left:
            self.queue[parent] = left
        else:
            self.queue.pop(parent, None)

    @contextmanager
    def waiting(self, parent: str | None) -> Iterator[None]:
        if not parent:
            yield
            return
        self.waits[parent] = self.waits.get(parent, 0) + 1
        try:
            yield
        finally:
            self.waits[parent] -= 1
            if self.waits[parent] <= 0:
                del self.waits[parent]

    def take_ready(self, panes: dict, now: float) -> list[tuple[str, str]]:
        """(parent id, text) for every parent that can take its notes now; those notes leave the queue."""
        ready = []
        for parent_id in list(self.queue):
            pane = panes.get(parent_id)
            if pane is None or not pane.alive:
                self.queue.pop(parent_id, None)
                continue
            if (pane.meta.kind == "shell" or pane.state == "blocked" or parent_id in self.waits
                    or parent_id in self.sending or pane.draft.blocks(now)):
                continue
            ready.append((parent_id, " ".join(format_note(n) for n in self.queue.pop(parent_id))))
        return ready


def format_note(note: _Note) -> str:
    what = {"done": f"finished; read it with: dr read {note.name}",
            "blocked": f"is waiting for the user to answer a prompt; see it with: dr read {note.name}",
            "exited": f"exited ({note.detail or 'no exit code'})"}[note.state]
    return f'<dr from="{note.child} {note.name}" state="{note.state}">{what}</dr>'
