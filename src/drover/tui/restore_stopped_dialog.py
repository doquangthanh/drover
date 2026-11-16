"""Modal listing panes from the previous session: resume, start fresh, or discard the ticked ones."""

from __future__ import annotations

import os
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import SelectionList, Static


def _short_cwd(cwd: str) -> str:
    home = os.path.expanduser("~")
    return "~" + cwd[len(home):] if cwd.startswith(home) else cwd


class RestoreStoppedDialog(ModalScreen["tuple[str, list[str]] | None"]):
    """Dismisses with ("resume" | "fresh" | "discard", ids) or None for "later"."""

    BINDINGS: ClassVar[list[Binding]] = [Binding("enter", "choose('resume')", "Resume", priority=True),
                Binding("f", "choose('fresh')", "Fresh", priority=True),
                Binding("d", "choose('discard')", "Discard", priority=True),
                Binding("escape", "later", "Later", priority=True)]
    DEFAULT_CSS = """
    RestoreStoppedDialog { align: center middle; }
    RestoreStoppedDialog > Vertical { width: 80%; max-width: 100; height: auto; max-height: 80%;
                                      border: round $accent; background: $surface; padding: 1 2; }
    """

    def __init__(self, stopped: list[dict]) -> None:
        super().__init__()
        self._stopped = stopped

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("[b]Panes from the previous session[/b]", markup=True)
            yield SelectionList[str](*[
                (f"{s['name'] or s['id']}  [dim]{s.get('command') or 'shell'}  {_short_cwd(s.get('cwd', ''))}[/dim]",
                 s["id"], True) for s in self._stopped])
            yield Static("[b]space[/b] tick  [b]enter[/b] resume  [b]f[/b] fresh start  [b]d[/b] discard  [b]esc[/b] later",
                         markup=True)

    def action_choose(self, how: str) -> None:
        ids = list(self.query_one(SelectionList).selected)
        self.dismiss((how, ids))

    def action_later(self) -> None:
        self.dismiss(None)
