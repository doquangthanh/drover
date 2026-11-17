"""Herdr-style sidebar: spaces on top (with the state that needs you most), agents below.

Each entry is two lines built from tokens, like Herdr's default layout; a token with no value disappears with its
separator, so no row ever shows an empty gap:

    ● drover                      ● drover · review
      main · ↑2 · ±3                claude-2

The open space and the focused agent get a row background; the list cursor only shows while the sidebar has focus.
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

SEP = " · "


class SpaceSelected(Message):
    def __init__(self, space_id: str) -> None:
        super().__init__()
        self.space_id = space_id


class PaneSelected(Message):
    def __init__(self, pane_id: str, tab_id: str) -> None:
        super().__init__()
        self.pane_id, self.tab_id = pane_id, tab_id


def _tokens(*values: str) -> str:
    """Join the values that exist with ' · '; missing ones leave no separator behind."""
    return SEP.join(v for v in values if v)


def _entry(lines: list[Text], width: int | None) -> Text:
    """One sidebar entry: each line cut to the width with '…'."""
    for line in lines:
        line.no_wrap = True
        if width:
            line.truncate(width, overflow="ellipsis")
    entry = Text("\n").join(lines)
    entry.no_wrap = True
    return entry


def space_rows(state: dict, current: str | None, width: int | None = None) -> list[tuple[str, Text]]:
    rows = []
    for space in state.get("spaces", []):
        states = [p["state"] for t in tabs_of(state, space["id"]) for p in panes_of(state, t)]
        glyph, style = state_glyph(worst_state(states))
        lines = [Text.assemble((glyph + " ", style), (space["name"], "bold"))]
        ahead, dirty = space.get("ahead") or 0, space.get("dirty") or 0
        git = _tokens(space.get("branch") or "", f"↑{ahead}" if ahead else "", f"±{dirty}" if dirty else "")
        if git:
            lines.append(Text("  " + git, "dim"))
        rows.append((space["id"], _entry(lines, width)))
    return rows


def agent_rows(state: dict, width: int | None = None) -> list[tuple[str, Text]]:
    spaces = {s["id"]: s["name"] for s in state.get("spaces", [])}
    rows = []
    for pane in state.get("panes", []):
        if (pane.get("kind") or "shell") == "shell":
            continue
        tab = tab_of_pane(state, pane["id"]) or {}
        glyph, style = state_glyph(pane["state"])
        name = pane["name"] or pane["id"]
        tab_name = tab.get("name") if tab.get("name") != name else ""  # a tab named after its pane says it twice
        lines = [Text.assemble((glyph + " ", style), _tokens(spaces.get(tab.get("space_id"), ""), tab_name or "")),
                 Text("  " + name, "bold")]
        rows.append((pane["id"], _entry(lines, width)))
    return rows


# OptionList padding (1 + 1) and room for a scrollbar, kept free whether or not it shows (it can briefly come up
# at Textual's default 2-cell size while the lists settle, and a row cut wider than that loses its '…').
LIST_CHROME = 4


def _row_width(sidebar: Vertical) -> int | None:
    """Cells a row can use, from the sidebar's own width (a list's width shifts while its scrollbar comes and
    goes, and the list does not tell us); None before the first layout (rows are cut again on resize)."""
    width = sidebar.content_region.width - LIST_CHROME
    return width if width > 0 else None


def _refill(widget: OptionList, rows: list[tuple[str, Text]], active: str | None, navigating: bool) -> None:
    """Replace the options. Normally the highlight sits on the open row (painted as the active-row background, full
    width by Textual itself); while you navigate the sidebar it stays where you put it. `navigating` comes from the
    app, not `has_focus`: switching tabs removes the focused pane and Textual parks the focus here for a moment."""
    keep = widget.get_option_at_index(widget.highlighted).id if widget.highlighted is not None else None
    widget.clear_options()
    widget.add_options([Option(label, id=oid) for oid, label in rows])
    ids = [oid for oid, _ in rows]
    target = keep if navigating else active
    widget.highlighted = ids.index(target) if target in ids else None


class WorkspaceSidebar(Vertical):
    DEFAULT_CSS = """
    WorkspaceSidebar .head { height: 1; padding: 0 1; color: $text-muted; text-style: bold; }
    WorkspaceSidebar #agents-head { margin-top: 1; }
    /* nowrap: a row one cell too wide (while the scrollbar shows) is clipped, never wrapped into an extra line. */
    WorkspaceSidebar OptionList {
        border: none; background: transparent; scrollbar-size-vertical: 1; text-wrap: nowrap; text-overflow: clip;
    }
    WorkspaceSidebar #spaces { height: auto; max-height: 50%; }
    WorkspaceSidebar #agents { height: 1fr; }
    /* Herdr: out of focus the highlight is the open space / focused agent (active_row_bg); in the sidebar it is
       the cursor you move (selection_bg). */
    WorkspaceSidebar OptionList > .option-list--option-highlighted {
        background: #262d38; color: $foreground; text-style: none;
    }
    WorkspaceSidebar OptionList:focus > .option-list--option-highlighted { background: $panel-lighten-2; }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._state: dict = {}
        self._current: tuple[str | None, str | None, bool] = (None, None, False)

    def compose(self) -> ComposeResult:
        yield Static("SPACES", classes="head")
        yield OptionList(id="spaces")
        yield Static("AGENTS", classes="head", id="agents-head")
        yield OptionList(id="agents")

    def rebuild(self, state: dict, current_space: str | None = None, current_pane: str | None = None,
                navigating: bool = False) -> None:
        self._state, self._current = state, (current_space, current_pane, navigating)
        width = _row_width(self)
        spaces, agents = self.query_one("#spaces", OptionList), self.query_one("#agents", OptionList)
        _refill(spaces, space_rows(state, current_space, width), current_space, navigating)
        _refill(agents, agent_rows(state, width), current_pane, navigating)

    def on_resize(self) -> None:
        self.call_after_refresh(self._rebuild_latest)

    def _rebuild_latest(self) -> None:
        """Re-cut the rows for the new width with the state as it is *now*: a newer rebuild may have run since."""
        if self._state:
            self.rebuild(self._state, *self._current)

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
