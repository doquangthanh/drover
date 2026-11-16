"""Status line and the "restore stopped panes" prompt. Mixed into `TuiApp`."""

from __future__ import annotations

from rich.text import Text
from textual.screen import ModalScreen
from textual.widgets import Static

from drover.tui.restore_logic import unasked_stopped
from drover.tui.restore_stopped_dialog import RestoreStoppedDialog
from drover.tui.tui_state_helpers import panes_of, state_glyph, worst_state


class StatusAndRestore:
    def update_status(self) -> None:
        tab = next((t for t in self.state["tabs"] if t["id"] == self.current_tab_id), None)
        text = Text()
        text.append("connected " if self.connected else "reconnecting… ", style="green" if self.connected else "bold red")
        if tab:
            panes = panes_of(self.state, tab)
            glyph, style = state_glyph(worst_state([p["state"] for p in panes]))
            text.append(f"{glyph} ", style=style)
            text.append(tab["name"])
            if self.mode == "narrow" and len(panes) > 1:
                index = next((i for i, p in enumerate(panes) if p["id"] == self.focused_pane), 0) + 1
                text.append(f"  {index}/{len(panes)} panes")
        if self.router.armed:
            text.append("  PREFIX", style="bold reverse")
        self.query_one("#status", Static).update(text)

    def _maybe_ask_restore(self) -> None:
        if isinstance(self.screen, ModalScreen):
            return
        pending = unasked_stopped(self.state.get("stopped", []), self._asked)
        if not pending:
            return
        self._asked.update(s["id"] for s in pending)  # ask once per pane per session, like the web UI

        def answered(result: tuple[str, list[str]] | None) -> None:
            if not result or not result[1]:
                return
            how, ids = result
            if how == "discard":
                self.call_rpc("session.discard", {"panes": ids})
            else:
                self.call_rpc("session.resume", {"panes": ids, "fresh": how == "fresh"})

        self.push_screen(RestoreStoppedDialog(pending), answered)


