"""Prefix-key state machine (tmux style). Pure: the app feeds it key presses and acts on the answer."""

from __future__ import annotations

ARMED_SECONDS = 2.0
ACTIONS = {
    "o": "next_pane", "left": "focus_left", "right": "focus_right", "up": "focus_up", "down": "focus_down",
    "z": "zoom", "%": "split_right", '"': "split_down", "x": "close_pane", "n": "next_blocked",
    "tab": "next_tab", "p": "prev_tab", "b": "toggle_sidebar", "r": "restore", "d": "quit", "?": "help",
    **{str(i): f"goto_tab_{i}" for i in range(1, 10)},
}


def to_textual_key(prefix: str) -> str:
    """Daemon setting `C-a` -> Textual key `ctrl+a`."""
    if prefix.lower().startswith("c-") and len(prefix) > 2:
        return "ctrl+" + prefix[2:].lower()
    return prefix.lower()


def literal_prefix(prefix: str) -> str:
    """The raw byte a pane receives when the prefix key is pressed twice (`C-a` -> \\x01)."""
    key = to_textual_key(prefix)
    return chr(ord(key[-1]) - 96) if key.startswith("ctrl+") and key[-1].isalpha() else ""


class PrefixKeyRouter:
    def __init__(self, prefix: str = "C-a") -> None:
        self.set_prefix(prefix)
        self._armed_at: float | None = None

    def set_prefix(self, prefix: str) -> None:
        self.prefix_key = to_textual_key(prefix)
        self.literal = literal_prefix(prefix)

    @property
    def armed(self) -> bool:
        return self._armed_at is not None

    def handle(self, key: str, character: str | None, now: float) -> tuple[str, str] | None:
        """None = not ours (let the pane have it). ("armed", "") / ("action", name) / ("literal", bytes) / ("cancel", "")."""
        if self._armed_at is not None and now - self._armed_at > ARMED_SECONDS:
            self._armed_at = None  # timeout: the prefix press is forgotten, this key is a normal key
        if self._armed_at is None:
            if key == self.prefix_key:
                self._armed_at = now
                return "armed", ""
            return None
        self._armed_at = None
        if key == self.prefix_key:
            return ("literal", self.literal) if self.literal else ("cancel", "")
        action = ACTIONS.get(character or "") or ACTIONS.get(key)
        return ("action", action) if action else ("cancel", "")
