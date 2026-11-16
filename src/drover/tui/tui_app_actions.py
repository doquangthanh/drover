"""What the prefix-key shortcuts do. Mixed into `TuiApp`; uses its `state`, `conn`, `layout` and focus helpers."""

from __future__ import annotations

from drover.core.split_layout_tree import pane_ids
from drover.tui.confirm_dialog import ConfirmDialog
from drover.tui.tui_state_helpers import next_blocked_pane, tab_of_pane

HELP = ("prefix o next pane, arrows move, z zoom, % split right, \" split down, x close, n next blocked,\n"
        "tab/p next/prev tab, 1-9 tab, b sidebar, r restore/restart, d quit (agents keep running), prefix prefix = literal")


class PrefixActions:
    def do_prefix_action(self, name: str) -> None:
        if name.startswith("goto_tab_"):
            return self._goto_tab(int(name.rsplit("_", 1)[1]) - 1)
        handler = getattr(self, f"_act_{name}", None)
        if handler:
            handler()

    def _tab(self) -> dict | None:
        return next((t for t in self.state.get("tabs", []) if t["id"] == self.current_tab_id), None)

    def _tab_panes(self) -> list[str]:
        tab = self._tab()
        return pane_ids(tab.get("layout")) if tab else []

    def _goto_tab(self, index: int) -> None:
        tabs = self.state.get("tabs", [])
        if tabs:
            self.show_tab(tabs[index % len(tabs)]["id"])

    def _step_tab(self, step: int) -> None:
        ids = [t["id"] for t in self.state.get("tabs", [])]
        if self.current_tab_id in ids:
            self.show_tab(ids[(ids.index(self.current_tab_id) + step) % len(ids)])

    def _act_next_tab(self) -> None:
        self._step_tab(1)

    def _act_prev_tab(self) -> None:
        self._step_tab(-1)

    def _act_next_pane(self) -> None:
        ids = self._tab_panes()
        if len(ids) > 1 and self.focused_pane in ids:
            self.focus_pane(ids[(ids.index(self.focused_pane) + 1) % len(ids)])

    def _move(self, direction: str) -> None:
        target = self.layout_view.neighbour(self.focused_pane or "", direction)
        if target:
            self.focus_pane(target)

    def _act_focus_left(self) -> None:
        self._move("left")

    def _act_focus_right(self) -> None:
        self._move("right")

    def _act_focus_up(self) -> None:
        self._move("up")

    def _act_focus_down(self) -> None:
        self._move("down")

    def _act_zoom(self) -> None:
        tab = self._tab()
        if tab:
            self.call_rpc("tab.zoom", {"tab": tab["id"], "zoomed": not tab.get("zoomed")})

    def _split(self, direction: str) -> None:
        if self.focused_pane:
            self.call_rpc("pane.split", {"pane": self.focused_pane, "direction": direction}, focus_result=True)

    def _act_split_right(self) -> None:
        self._split("right")

    def _act_split_down(self) -> None:
        self._split("down")

    def _act_close_pane(self) -> None:
        pane = self.focused_pane
        if not pane:
            return
        stopped = pane not in {p["id"] for p in self.state.get("panes", [])}

        def answered(yes: bool | None) -> None:
            if yes:
                if stopped:
                    self.call_rpc("session.discard", {"panes": [pane]})
                else:
                    self.call_rpc("pane.close", {"pane": pane})

        self.push_screen(ConfirmDialog(f"Close {pane}? The agent is stopped."), answered)

    def _act_next_blocked(self) -> None:
        target = next_blocked_pane(self.state, self.focused_pane)
        tab = tab_of_pane(self.state, target) if target else None
        if tab:
            self.show_tab(tab["id"], pane=target)

    def _act_toggle_sidebar(self) -> None:
        self.toggle_sidebar()

    def _act_restore(self) -> None:
        pane = self.focused_pane
        if not pane:
            return
        if pane in {s["id"] for s in self.state.get("stopped", [])}:
            self.call_rpc("session.resume", {"panes": [pane]})
        else:
            self.call_rpc("pane.restart", {"pane": pane, "resume": True})

    def _act_quit(self) -> None:
        self.exit()

    def _act_help(self) -> None:
        self.notify(HELP, title="Prefix keys", timeout=10)


__all__ = ["PrefixActions"]
