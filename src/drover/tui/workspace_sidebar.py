"""Herdr-style sidebar: spaces on top (with the state that needs you most), agents below.

A plain shell is not listed under Agents; it shows up once claude/codex/... runs in it.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from drover.tui.tui_state_helpers import panes_of, state_glyph, tab_of_pane, tabs_of, worst_state


class SpaceSelected(Message):
    def __init__(self, space_id: str) -> None:
        super().__init__()
        self.space_id = space_id


class PaneSelected(Message):
    def __init__(self, pane_id: str, tab_id: str) -> None:
        super().__init__()
        self.pane_id, self.tab_id = pane_id, tab_id


def space_rows(state: dict, current: str | None) -> list[tuple[str, Text]]:
    rows = []
    for space in state.get("spaces", []):
        states = [p["state"] for t in tabs_of(state, space["id"]) for p in panes_of(state, t)]
        glyph, style = state_glyph(worst_state(states))
        bold = "bold reverse" if space["id"] == current else "bold"
        rows.append((space["id"], Text.assemble((glyph + " ", style), (space["name"], bold))))
    return rows


def agent_rows(state: dict) -> list[tuple[str, Text]]:
    spaces = {s["id"]: s["name"] for s in state.get("spaces", [])}
    rows = []
    for pane in state.get("panes", []):
        if (pane.get("kind") or "shell") == "shell":
            continue
        tab = tab_of_pane(state, pane["id"]) or {}
        glyph, style = state_glyph(pane["state"])
        rows.append((pane["id"], Text.assemble((glyph + " ", style), pane["name"] or pane["id"],
                                               (f"  {spaces.get(tab.get('space_id'), '')}", "dim"))))
    return rows


def _refill(widget: OptionList, rows: list[tuple[str, Text]]) -> None:
    """Replace the options but keep the highlighted row on the same id."""
    keep = widget.get_option_at_index(widget.highlighted).id if widget.highlighted is not None else None
    widget.clear_options()
    widget.add_options([Option(label, id=oid) for oid, label in rows])
    ids = [oid for oid, _ in rows]
    widget.highlighted = ids.index(keep) if keep in ids else (0 if ids else None)


class WorkspaceSidebar(Vertical):
    DEFAULT_CSS = """
    WorkspaceSidebar .head { height: 1; padding: 0 1; color: $text-muted; text-style: bold; }
    WorkspaceSidebar OptionList { border: none; height: 1fr; background: transparent; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._state: dict = {}

    def compose(self) -> ComposeResult:
        yield Static("SPACES", classes="head")
        yield OptionList(id="spaces")
        yield Static("AGENTS", classes="head")
        yield OptionList(id="agents")

    def rebuild(self, state: dict, current_space: str | None = None) -> None:
        self._state = state
        _refill(self.query_one("#spaces", OptionList), space_rows(state, current_space))
        _refill(self.query_one("#agents", OptionList), agent_rows(state))

    def labels(self) -> str:
        """Plain text of both lists (tests)."""
        return " ".join(str(w.get_option_at_index(i).prompt) for w in self.query(OptionList)
                        for i in range(w.option_count))

    def focus(self, scroll_visible: bool = True) -> WorkspaceSidebar:
        self.query_one("#spaces", OptionList).focus(scroll_visible)
        return self

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        oid = event.option.id or ""
        if event.option_list.id == "spaces":
            self.post_message(SpaceSelected(oid))
        else:
            tab = tab_of_pane(self._state, oid)
            self.post_message(PaneSelected(oid, tab["id"] if tab else ""))
