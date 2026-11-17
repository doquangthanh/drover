"""Pure helpers over the daemon's state snapshot (`spaces`, `tabs`, `panes`, `stopped`): no Textual, easy to test."""

from __future__ import annotations

from typing import Any

from drover.core.split_layout_tree import pane_ids

# worst first: what the user must look at beats what is merely running
STATE_PRIORITY = ["blocked", "done", "working", "idle", "exited", "stopped"]
# Same colours as the app's state dots (web UI dark theme: --working, --blocked, --done).
GLYPHS = {"working": ("●", "#76a8ff"), "blocked": ("!", "bold #f2a33c"), "done": ("✓", "bold #4cc48c"),
          "idle": ("○", "dim"), "exited": ("×", "dim"), "stopped": ("×", "dim")}
# The app's accent (--accent / --on-accent, dark theme): open tab, open space, mode markers (PREFIX, SCROLL).
ACCENT = "#96b2d7"
ACCENT_CHIP = f"bold #101114 on {ACCENT}"


def worst_state(states: list[str]) -> str:
    known = [s for s in states if s in STATE_PRIORITY]
    return min(known, key=STATE_PRIORITY.index) if known else "idle"


def state_glyph(state: str) -> tuple[str, str]:
    """(character, Rich style)."""
    return GLYPHS.get(state, GLYPHS["idle"])


def tabs_of(state: dict, space_id: str) -> list[dict]:
    return [t for t in state.get("tabs", []) if t["space_id"] == space_id]


def panes_by_id(state: dict) -> dict[str, dict]:
    return {p["id"]: p for p in state.get("panes", [])}


def stopped_by_id(state: dict) -> dict[str, dict]:
    return {s["id"]: s for s in state.get("stopped", [])}


def panes_of(state: dict, tab: dict) -> list[dict[str, Any]]:
    """Live and stopped panes of a tab, in layout order. Each stopped entry gets `state: "stopped"`."""
    live, stopped = panes_by_id(state), stopped_by_id(state)
    out: list[dict[str, Any]] = []
    for pid in pane_ids(tab.get("layout")):
        if pid in live:
            out.append(live[pid])
        elif pid in stopped:
            out.append({**stopped[pid], "state": "stopped"})
    return out


def tab_state(state: dict, tab: dict) -> str:
    return worst_state([p["state"] for p in panes_of(state, tab)])


def tab_of_pane(state: dict, pane_id: str) -> dict | None:
    return next((t for t in state.get("tabs", []) if pane_id in pane_ids(t.get("layout"))), None)


def default_tab_id(state: dict) -> str | None:
    """Tab of the pane the user focused last (the daemon keeps `focused` per tab), else the first tab."""
    tabs = state.get("tabs", [])
    live = panes_by_id(state)
    for tab in reversed(tabs):
        if tab.get("focused") in live and live[tab["focused"]].get("unread") is False:
            return tab["id"]
    return tabs[0]["id"] if tabs else None


def focused_pane_id(tab: dict) -> str | None:
    ids = pane_ids(tab.get("layout"))
    return tab.get("focused") if tab.get("focused") in ids else (ids[0] if ids else None)


def next_blocked_pane(state: dict, after: str | None) -> str | None:
    blocked = [p["id"] for p in state.get("panes", []) if p["state"] == "blocked"]
    if not blocked:
        return None
    return blocked[(blocked.index(after) + 1) % len(blocked)] if after in blocked else blocked[0]
