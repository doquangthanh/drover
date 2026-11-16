"""`dr tui`: the Textual client. Structure comes from daemon events, terminal bytes go straight to the pane views."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from textual import events
from textual.app import App, ComposeResult
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.timer import Timer
from textual.widgets import Static

from drover.tui.daemon_ws_connection import DaemonConnection, RpcError
from drover.tui.prefix_key_router import PrefixKeyRouter
from drover.tui.responsive_mode import mode_for
from drover.tui.split_layout_view import MIN_COLS, MIN_ROWS, SplitLayoutView
from drover.tui.tui_app_actions import PrefixActions
from drover.tui.tui_app_status_and_restore import StatusAndRestore
from drover.tui.tui_messages import ConnectionChanged, PaneChanged, PaneStatusChanged, StateChanged
from drover.tui.tui_state_helpers import (
    default_tab_id,
    focused_pane_id,
    panes_of,
    tab_of_pane,
)
from drover.tui.workspace_sidebar import PaneSelected, TabSelected, WorkspaceSidebar

REFRESH_SECONDS = 0.1


class TuiApp(PrefixActions, StatusAndRestore, App):
    CSS_PATH = Path(__file__).with_name("tui.tcss")
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, conn: DaemonConnection) -> None:
        super().__init__()
        self.conn = conn
        self.state: dict = {"spaces": [], "tabs": [], "panes": [], "stopped": []}
        self.router = PrefixKeyRouter()
        self.current_tab_id: str | None = None
        self.focused_pane: str | None = None
        self.mode = "wide"
        self.sidebar_hidden = False  # wide mode: user hid the docked sidebar
        self.sidebar_open = False  # medium/narrow: sidebar overlay is showing
        self.sidebar_active = False  # the user moved the keyboard focus to the sidebar on purpose
        self.connected = False
        self._asked: set[str] = set()
        self._pending_focus: str | None = None
        self._refresh_timer: Timer | None = None
        self._refresh_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task] = set()

    def compose(self) -> ComposeResult:
        with Container(id="root"):
            yield WorkspaceSidebar(id="sidebar")
            with Vertical(id="body"):
                yield SplitLayoutView(on_input=self.conn.send_input, on_size=self._pane_size,
                                      on_attach=self.conn.attach, on_detach=self.conn.detach, id="layout")
                yield Static("", id="status")

    @property
    def layout_view(self) -> SplitLayoutView:
        return self.query_one("#layout", SplitLayoutView)

    def on_mount(self) -> None:
        conn = self.conn
        conn.on_state = lambda s: self.post_message(StateChanged(s))
        conn.on_status = lambda d: self.post_message(PaneStatusChanged(d["pane"], d["old"], d["new"]))
        conn.on_pane = lambda p: self.post_message(PaneChanged(p))
        conn.on_connection = lambda ok: self.post_message(ConnectionChanged(ok))
        conn.on_output = lambda pane, data, replay: self.layout_view.route_output(pane, data, replay)
        self.mode = mode_for(*self.size)
        self._apply_mode()
        self.run_worker(conn.run(), exit_on_error=False)

    def on_unmount(self) -> None:
        self.conn.stop()

    # -- events from the daemon -----------------------------------------------------
    def on_state_changed(self, msg: StateChanged) -> None:
        self.state = msg.state
        self.router.set_prefix(msg.state.get("prefix", "C-a"))
        self.schedule_refresh()

    def on_pane_status_changed(self, msg: PaneStatusChanged) -> None:
        self._patch_pane(msg.pane)

    def on_pane_changed(self, msg: PaneChanged) -> None:
        self._patch_pane(msg.pane)

    def on_connection_changed(self, msg: ConnectionChanged) -> None:
        self.connected = msg.connected
        self.update_status()

    def _patch_pane(self, pane: dict) -> None:
        panes = self.state["panes"]
        for i, old in enumerate(panes):
            if old["id"] == pane["id"]:
                panes[i] = pane
                self.schedule_refresh()
                return

    # -- refresh (coalesced) --------------------------------------------------------
    def schedule_refresh(self) -> None:
        if self._refresh_timer is None:
            self._refresh_timer = self.set_timer(REFRESH_SECONDS, self.refresh_now)

    async def refresh_now(self) -> None:
        self._refresh_timer = None
        async with self._refresh_lock:
            state = self.state
            tabs = {t["id"]: t for t in state["tabs"]}
            if self.current_tab_id not in tabs:
                self.current_tab_id = default_tab_id(state)
            tab = tabs.get(self.current_tab_id)
            if tab and self._pending_focus in dict.fromkeys(p["id"] for p in panes_of(state, tab)):
                self._set_focus(tab, self._pending_focus)
                self._pending_focus = None
            elif tab and self.focused_pane not in {p["id"] for p in panes_of(state, tab)}:
                self.focused_pane = focused_pane_id(tab)
            elif tab and self.focused_pane:
                tab["focused"] = self.focused_pane
            rebuilt = await self.layout_view.show_tab(tab, state, single=self.mode == "narrow")
            self.query_one(WorkspaceSidebar).rebuild(state)
            self.update_status()
            if rebuilt and self.focused_pane and not self.sidebar_active:
                self.call_after_refresh(self.layout_view.focus_pane, self.focused_pane)
            self._maybe_ask_restore()

    # -- selection and focus --------------------------------------------------------
    def show_tab(self, tab_id: str, pane: str | None = None) -> None:
        self.current_tab_id = tab_id
        self._pending_focus = pane
        self.focused_pane = None
        self.run_worker(self.refresh_now(), exclusive=False)

    def focus_pane(self, pane_id: str) -> None:
        tab = tab_of_pane(self.state, pane_id)
        if tab is None:
            return
        self._set_focus(tab, pane_id)
        self.call_rpc("pane.focus", {"pane": pane_id}) if pane_id in {p["id"] for p in self.state["panes"]} else None
        self.run_worker(self.refresh_now(), exclusive=False)
        self.call_after_refresh(self.layout_view.focus_pane, pane_id)

    def _set_focus(self, tab: dict, pane_id: str) -> None:
        self.focused_pane = pane_id
        tab["focused"] = pane_id  # the daemon updates its own copy, but only emits a `pane` event: keep ours in step

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        pane_id = getattr(event.widget, "pane_id", None)
        if pane_id and pane_id != self.focused_pane:
            self.focus_pane(pane_id)

    def on_tab_selected(self, msg: TabSelected) -> None:
        self.sidebar_open = self.sidebar_active = False
        self.show_tab(msg.tab_id)
        self._apply_mode()

    def on_pane_selected(self, msg: PaneSelected) -> None:
        self.sidebar_open = self.sidebar_active = False
        self.show_tab(msg.tab_id, pane=msg.pane_id)
        self._apply_mode()

    # -- layout mode ----------------------------------------------------------------
    def on_resize(self, event: events.Resize) -> None:
        mode = mode_for(event.size.width, event.size.height)
        if mode != self.mode:
            self.mode = mode
            self._apply_mode()
            self.schedule_refresh()

    def _apply_mode(self) -> None:
        root = self.query_one("#root")
        root.set_class(self.mode == "wide" and not self.sidebar_hidden, "-wide")
        root.set_class(self.mode != "wide" and self.sidebar_open, "-overlay")

    def toggle_sidebar(self) -> None:
        """Wide: hidden -> shown+focused -> (focused) hidden. Medium/narrow: overlay on/off."""
        shown = self.mode == "wide" and not self.sidebar_hidden or self.sidebar_open
        if shown and (self.sidebar_active or self.mode != "wide"):
            self.sidebar_active = self.sidebar_open = False
            self.sidebar_hidden = self.mode == "wide"
            if self.focused_pane:
                self.layout_view.focus_pane(self.focused_pane)
        else:
            self.sidebar_hidden = False
            self.sidebar_open = self.mode != "wide"
            self.sidebar_active = True
            self.query_one(WorkspaceSidebar).focus()
        self._apply_mode()

    # -- keys -----------------------------------------------------------------------
    async def on_event(self, event: events.Event) -> None:
        if isinstance(event, events.Key):
            if isinstance(self.screen, ModalScreen):
                pass
            elif event.key == "ctrl+q":  # Textual would quit; the pane gets it (quit is prefix d)
                if self.focused_pane:
                    self.conn.send_input(self.focused_pane, "\x11")
                return
            elif self._handle_prefix(event):
                return
        await super().on_event(event)

    def _handle_prefix(self, event: events.Key) -> bool:
        result = self.router.handle(event.key, event.character, time.monotonic())
        if result is None:
            return False
        kind, value = result
        if kind == "action":
            self.do_prefix_action(value)
        elif kind == "literal" and self.focused_pane:
            self.conn.send_input(self.focused_pane, value)
        self.update_status()
        if kind == "armed":
            self.set_timer(2.1, self.update_status)  # clear the PREFIX marker when it times out
        return True

    # -- rpc helpers ----------------------------------------------------------------
    def call_rpc(self, method: str, params: dict, focus_result: bool = False) -> None:
        async def go() -> None:
            try:
                result = await self.conn.rpc(method, params)
            except RpcError as exc:
                self.notify(f"{method}: {exc}", severity="error")
                return
            if focus_result and isinstance(result, dict) and result.get("pane"):
                self._pending_focus = result["pane"]["id"]

        task = asyncio.ensure_future(go())
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _pane_size(self, pane_id: str, cols: int, rows: int) -> None:
        if cols >= MIN_COLS and rows >= MIN_ROWS:  # smaller would be clamped by the daemon anyway
            self.call_rpc("pane.resize", {"pane": pane_id, "cols": cols, "rows": rows})


def main() -> int:
    from drover.daemon.daemon_client import ensure_daemon

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    info = ensure_daemon()
    TuiApp(DaemonConnection(f"http://127.0.0.1:{info['port']}", info["token"])).run()
    return 0
