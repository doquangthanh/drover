"""Small Y/N modal."""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static


class ConfirmDialog(ModalScreen[bool]):
    BINDINGS: ClassVar[list[Binding]] = [Binding("y", "answer(True)", "Yes", priority=True), Binding("enter", "answer(True)", "Yes", priority=True),
                Binding("n", "answer(False)", "No", priority=True), Binding("escape", "answer(False)", "No", priority=True)]
    DEFAULT_CSS = """
    ConfirmDialog { align: center middle; }
    ConfirmDialog > Vertical { width: 50; height: auto; border: round $warning; background: $surface; padding: 1 2; }
    """

    def __init__(self, question: str) -> None:
        super().__init__()
        self._question = question

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self._question)
            yield Static("[b]y[/b] yes   [b]n[/b] no", markup=True)

    def action_answer(self, value: bool) -> None:
        self.dismiss(value)
