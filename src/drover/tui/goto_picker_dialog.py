"""Herdr's goto picker (prefix+g): every agent and terminal on one row, the ones that need you first.

Type to filter by name, kind, space or tab; Enter jumps there, Esc closes.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, OptionList
from textual.widgets.option_list import Option

from drover.tui.tui_state_helpers import STATE_PRIORITY, state_glyph, tab_of_pane


def picker_rows(state: dict) -> list[tuple[str, str, str]]:
    """(pane id, search text, label) for every live pane: blocked first, then done, working, idle."""
    spaces = {s["id"]: s["name"] for s in state.get("spaces", [])}
    rows = []
    for pane in state.get("panes", []):
        tab = tab_of_pane(state, pane["id"]) or {}
        where = f"{spaces.get(tab.get('space_id'), '?')} / {tab.get('name', '?')}"
        kind = pane.get("kind") or "shell"
        rows.append((pane["id"], f"{pane['name']} {kind} {where}".lower(), pane["state"], pane["name"], kind, where))
    rank = {s: i for i, s in enumerate(STATE_PRIORITY)}
    rows.sort(key=lambda r: rank.get(r[2], 99))
    out = []
    for pid, search, st, name, kind, where in rows:
        glyph, style = state_glyph(st)
        label = Text.assemble((glyph + " ", style), (name, "bold"), f"  {kind}  ", (where, "dim"))
        out.append((pid, search, label))
    return out


class GotoPickerDialog(ModalScreen["str | None"]):
    BINDINGS: ClassVar[list[Binding]] = [Binding("escape", "cancel", "Cancel", priority=True),
                                         Binding("down", "move(1)", show=False, priority=True),
                                         Binding("up", "move(-1)", show=False, priority=True)]
    DEFAULT_CSS = """
    GotoPickerDialog { align: center middle; }
    GotoPickerDialog > Vertical { width: 70; height: 20; border: round $accent; background: $surface; }
    GotoPickerDialog OptionList { height: 1fr; border: none; }
    """

    def __init__(self, state: dict) -> None:
        super().__init__()
        self._rows = picker_rows(state)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Input(placeholder="Go to agent or terminal…", id="filter")
            yield OptionList(id="choices")

    def on_mount(self) -> None:
        self._fill("")

    def _fill(self, query: str) -> None:
        choices = self.query_one(OptionList)
        choices.clear_options()
        choices.add_options([Option(label, id=pid) for pid, search, label in self._rows if query in search])
        choices.highlighted = 0 if choices.option_count else None

    def on_input_changed(self, event: Input.Changed) -> None:
        self._fill(event.value.strip().lower())

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        choices = self.query_one(OptionList)
        if choices.highlighted is not None:
            self.dismiss(choices.get_option_at_index(choices.highlighted).id)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def action_move(self, step: int) -> None:
        choices = self.query_one(OptionList)
        if choices.option_count:
            choices.highlighted = ((choices.highlighted or 0) + step) % choices.option_count

    def action_cancel(self) -> None:
        self.dismiss(None)
