"""One-line text prompt (rename a tab or a space). Enter submits, Esc cancels."""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Static


class TextInputDialog(ModalScreen["str | None"]):
    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "cancel", "Cancel", priority=True)]
    DEFAULT_CSS = """
    TextInputDialog { align: center middle; }
    TextInputDialog > Vertical { width: 50; height: auto; border: round $accent; background: $surface; padding: 1 2; }
    """

    def __init__(self, title: str, value: str = "") -> None:
        super().__init__()
        self._title, self._value = title, value

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._title)
            yield Input(self._value, id="text")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.dismiss(event.value.strip() or None)

    def action_cancel(self) -> None:
        self.dismiss(None)
