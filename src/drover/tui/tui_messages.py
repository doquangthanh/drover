"""Textual messages the connection's callbacks post to the app (structure events only; terminal output bypasses these)."""

from __future__ import annotations

from textual.message import Message


class StateChanged(Message):
    def __init__(self, state: dict) -> None:
        super().__init__()
        self.state = state


class PaneStatusChanged(Message):
    """`status` event: one pane moved from `old` to `new` state (`pane` is its full dict)."""

    def __init__(self, pane: dict, old: str, new: str) -> None:
        super().__init__()
        self.pane, self.old, self.new = pane, old, new


class ConnectionChanged(Message):
    def __init__(self, connected: bool) -> None:
        super().__init__()
        self.connected = connected


class PaneChanged(Message):
    """`pane` event: one pane's fields changed (state, unread, title...)."""

    def __init__(self, pane: dict) -> None:
        super().__init__()
        self.pane = pane
