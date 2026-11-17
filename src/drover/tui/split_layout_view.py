"""Draws one tab: its split tree as nested containers, a live terminal (or a stopped placeholder) at each leaf."""

from __future__ import annotations

import json
from collections.abc import Callable

from textual.containers import Container, Horizontal, Vertical
from textual.markup import escape
from textual.widget import Widget
from textual.widgets import Static

from drover.core.split_layout_tree import pane_ids
from drover.tui.terminal_pane_view import TerminalPaneView
from drover.tui.tui_state_helpers import focused_pane_id, panes_by_id, state_glyph, stopped_by_id

MIN_COLS, MIN_ROWS = 10, 3  # the daemon clamps below this; never ask for less


def pane_title(state: str, name: str) -> str:
    """Border title markup: the state glyph in its app colour, then the (escaped) pane name."""
    glyph, style = state_glyph(state)
    return f"[{style}]{glyph}[/] {escape(name)}"


class StoppedPaneView(Static, can_focus=True):
    """Placeholder for a pane from the previous session that is not running."""

    DEFAULT_CSS = "StoppedPaneView { width: 1fr; height: 1fr; content-align: center middle; color: $text-muted; }"

    def __init__(self, pane_id: str, name: str) -> None:
        super().__init__(f"{name or pane_id}\nstopped. Prefix r restores it", markup=False)
        self.pane_id = pane_id


def layout_signature(tab: dict, single: str | None, stopped: set[str]) -> str:
    """Rebuild the widget tree only when this changes (not on every status event)."""
    return json.dumps([tab["id"], tab.get("layout"), single, sorted(stopped)], sort_keys=True)


def build_layout(node: dict, make_leaf: Callable[[str], Widget], only: str | None = None) -> Widget:
    """Binary tree -> nested Horizontal/Vertical with `fr` sizes from the ratio. `only` = just that one leaf (zoom)."""
    if only is not None:
        return make_leaf(only)
    if "pane" in node:
        return make_leaf(node["pane"])
    ratio = min(max(float(node.get("ratio", 0.5)), 0.05), 0.95)
    horizontal = node["split"] == "row"  # "row" = side by side
    first, second = build_layout(node["a"], make_leaf), build_layout(node["b"], make_leaf)
    # integer fr weights: Textual fr units accept floats, but ints keep rounding predictable
    a, b = max(1, round(ratio * 100)), max(1, round((1 - ratio) * 100))
    prop = "width" if horizontal else "height"
    setattr(first.styles, prop, f"{a}fr")
    setattr(second.styles, prop, f"{b}fr")
    box = Horizontal if horizontal else Vertical
    return box(first, second)


class SplitLayoutView(Container):
    DEFAULT_CSS = "SplitLayoutView { width: 1fr; height: 1fr; }"

    def __init__(self, on_input: Callable[[str, str], None], on_size: Callable[[str, int, int], None],
                 on_attach: Callable[[str], None], on_detach: Callable[[str], None], **kwargs) -> None:
        super().__init__(**kwargs)
        self._on_input, self._on_size = on_input, on_size
        self._on_attach, self._on_detach = on_attach, on_detach
        self.views: dict[str, TerminalPaneView] = {}
        self.stopped_views: dict[str, StoppedPaneView] = {}
        self._signature: str | None = None
        self.visible_ids: list[str] = []
        self.tab_id: str | None = None

    async def show_tab(self, tab: dict | None, state: dict, single: bool) -> bool:
        """Show `tab`. `single` = only its focused pane (zoom, or a narrow terminal). True when the widgets were rebuilt."""
        if tab is None:
            await self._clear()
            return False
        only = focused_pane_id(tab) if (single or tab.get("zoomed")) else None
        stopped = set(stopped_by_id(state))
        signature = layout_signature(tab, only, stopped & set(pane_ids(tab.get("layout"))))
        rebuilt = signature != self._signature
        if rebuilt:
            self._signature = signature
            await self._rebuild(tab, state, only)
        self.tab_id = tab["id"]
        # Herdr's "auto" borders: a lone pane fills the area; a frame (with its title) only tells split panes apart.
        self.set_class(len(self.visible_ids) == 1, "-single")
        self.refresh_titles(state)
        return rebuilt

    async def _clear(self) -> None:
        self._signature, self.tab_id = None, None
        for pid in list(self.views):
            self._on_detach(pid)
        self.views.clear()
        self.stopped_views.clear()
        self.visible_ids = []
        await self.remove_children()

    async def _rebuild(self, tab: dict, state: dict, only: str | None) -> None:
        live, stopped = panes_by_id(state), stopped_by_id(state)
        old_views = set(self.views)
        self.views, self.stopped_views = {}, {}

        def make_leaf(pid: str) -> Widget:
            if pid in live:
                view = TerminalPaneView(on_input=lambda data, p=pid: self._on_input(p, data),
                                        on_size=lambda c, r, p=pid: self._on_size(p, c, r))
                view.pane_id = pid
                self.views[pid] = view
                return view
            placeholder = StoppedPaneView(pid, stopped.get(pid, {}).get("name", ""))
            self.stopped_views[pid] = placeholder
            return placeholder

        layout = tab.get("layout")
        await self.remove_children()
        if layout:
            await self.mount(build_layout(layout, make_leaf, only))
        self.visible_ids = [pid for pid in pane_ids(layout) if pid in self.views or pid in self.stopped_views]
        for pid in old_views - set(self.views):
            self._on_detach(pid)
        for pid in set(self.views) - old_views:
            self._on_attach(pid)
        for pid in set(self.views) & old_views:  # the view was rebuilt: ask for a fresh replay
            self._on_attach(pid)

    def refresh_titles(self, state: dict) -> None:
        live, stopped = panes_by_id(state), stopped_by_id(state)
        for pid, view in self.views.items():
            pane = live.get(pid)
            if pane:
                view.border_title = pane_title(pane["state"], pane["name"] or pid)
        for pid, view in self.stopped_views.items():
            view.border_title = pane_title("stopped", stopped.get(pid, {}).get("name") or pid)

    def route_output(self, pane_id: str, data: str, replay: bool) -> None:
        view = self.views.get(pane_id)
        if view is not None:
            view.feed(data, replay)

    def widget_for(self, pane_id: str) -> Widget | None:
        return self.views.get(pane_id) or self.stopped_views.get(pane_id)

    def focus_pane(self, pane_id: str) -> None:
        widget = self.widget_for(pane_id)
        if widget is not None:
            widget.focus()

    def neighbour(self, current: str, direction: str) -> str | None:
        """Nearest visible pane in `direction` ("left"/"right"/"up"/"down") by on-screen position."""
        here = self.widget_for(current)
        if here is None:
            return None
        cx, cy = here.region.center
        best: tuple[float, str] | None = None
        for pid in self.visible_ids:
            widget = self.widget_for(pid)
            if pid == current or widget is None:
                continue
            x, y = widget.region.center
            dx, dy = x - cx, y - cy
            ok = {"left": dx < 0, "right": dx > 0, "up": dy < 0, "down": dy > 0}[direction]
            if ok:
                distance = dx * dx + dy * dy
                if best is None or distance < best[0]:
                    best = (distance, pid)
        return best[1] if best else None
