"""Herdr's tab and workspace keys: new / rename / close tab and space, goto picker, swap, copy mode.

Mixed into `TuiApp`; uses its `state`, `call_rpc`, `show_tab`, focus helpers and `layout_view`.
"""

from __future__ import annotations

import os

from drover.tui.confirm_dialog import ConfirmDialog
from drover.tui.goto_picker_dialog import GotoPickerDialog
from drover.tui.terminal_pane_view import TerminalPaneView
from drover.tui.text_input_dialog import TextInputDialog
from drover.tui.tui_state_helpers import tab_of_pane, tabs_of


class WorkspaceActions:
    def current_space_id(self) -> str | None:
        tab = self._tab()
        return tab["space_id"] if tab else None

    def _space(self) -> dict | None:
        sid = self.current_space_id()
        return next((s for s in self.state.get("spaces", []) if s["id"] == sid), None)

    # -- spaces ----------------------------------------------------------------------
    def ensure_first_space(self) -> None:
        """Herdr: a session with no workspace opens one, in the folder `dr` was started from."""
        if self._first_space_asked or self.state.get("spaces"):
            return
        self._first_space_asked = True
        self.call_rpc("space.create", {"new": True, "cwd": os.getcwd()}, focus_result=True)

    def _act_new_space(self) -> None:
        params = {"new": True, "from": self.focused_pane} if self.focused_pane else {"new": True, "cwd": os.getcwd()}
        self.call_rpc("space.create", params, focus_result=True)

    def _act_rename_space(self) -> None:
        space = self._space()
        if space:
            self.push_screen(TextInputDialog("Rename space", space["name"]),
                             lambda name: name and self.call_rpc("space.rename", {"space": space["id"], "name": name}))

    def _act_close_space(self) -> None:
        space = self._space()
        if not space:
            return

        def answered(yes: bool | None) -> None:
            if yes:
                self.call_rpc("space.remove", {"space": space["id"]})

        self.push_screen(ConfirmDialog(f"Close space {space['name']}? Every terminal in it stops."), answered)

    def select_space(self, space_id: str) -> None:
        tabs = tabs_of(self.state, space_id)
        if tabs:
            self.show_tab(tabs[0]["id"])

    # -- tabs ------------------------------------------------------------------------
    def _act_new_tab(self) -> None:
        sid = self.current_space_id()
        if sid:
            self.call_rpc("tab.create", {"space": sid}, focus_result=True)
        else:
            self._act_new_space()

    def _act_rename_tab(self) -> None:
        tab = self._tab()
        if tab:
            self.push_screen(TextInputDialog("Rename tab", tab["name"]),
                             lambda name: name and self.call_rpc("tab.rename", {"tab": tab["id"], "name": name}))

    def _act_close_tab(self) -> None:
        tab = self._tab()
        if not tab:
            return

        def answered(yes: bool | None) -> None:
            if yes:
                self.call_rpc("tab.close", {"tab": tab["id"]})

        self.push_screen(ConfirmDialog(f"Close tab {tab['name']}? Every terminal in it stops."), answered)

    # -- navigation ------------------------------------------------------------------
    def _act_goto(self) -> None:
        def chosen(pane_id: str | None) -> None:
            tab = tab_of_pane(self.state, pane_id) if pane_id else None
            if tab:
                self.show_tab(tab["id"], pane=pane_id)

        self.push_screen(GotoPickerDialog(self.state), chosen)

    def _act_focus_sidebar(self) -> None:
        if not self.sidebar_active:
            self.toggle_sidebar()

    def _swap(self, direction: str) -> None:
        target = self.layout_view.neighbour(self.focused_pane or "", direction)
        if target:
            self.call_rpc("pane.swap", {"pane": self.focused_pane, "target": target})

    def _act_swap_left(self) -> None:
        self._swap("left")

    def _act_swap_right(self) -> None:
        self._swap("right")

    def _act_swap_up(self) -> None:
        self._swap("up")

    def _act_swap_down(self) -> None:
        self._swap("down")

    def _act_scroll_mode(self) -> None:
        view = self.layout_view.widget_for(self.focused_pane or "")
        if isinstance(view, TerminalPaneView):
            view.on_scroll_mode = self.update_status
            view.set_scroll_mode(True)


__all__ = ["WorkspaceActions"]
