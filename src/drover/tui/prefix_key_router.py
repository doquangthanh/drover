"""Prefix-key state machine (tmux style). Pure: the app feeds it key presses and acts on the answer."""

from __future__ import annotations

ARMED_SECONDS = 2.0
# Herdr's default map (herdr.dev/docs/keyboard). Drover extras: r restore, a next agent that needs you, ? help.
ACTIONS = {
    # panes
    "v": "split_right", "-": "split_down", "minus": "split_down", "%": "split_right", '"': "split_down",
    "h": "focus_left", "j": "focus_down", "k": "focus_up", "l": "focus_right",
    "left": "focus_left", "down": "focus_down", "up": "focus_up", "right": "focus_right", "o": "next_pane",
    "H": "swap_left", "J": "swap_down", "K": "swap_up", "L": "swap_right",
    "z": "zoom", "x": "close_pane", "[": "scroll_mode",
    # tabs
    "c": "new_tab", "n": "next_tab", "p": "prev_tab", "tab": "next_tab",
    "T": "rename_tab", "X": "close_tab",
    **{str(i): f"goto_tab_{i}" for i in range(1, 10)},
    # workspaces (spaces)
    "N": "new_space", "W": "rename_space", "D": "close_space", "w": "focus_sidebar", "g": "goto",
    "b": "toggle_sidebar", "q": "quit", "d": "quit",
    # drover
    "a": "next_blocked", "r": "restore", "?": "help",
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
    def __init__(self, prefix: str = "C-b") -> None:
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
