"""Status line and the "restore stopped panes" prompt. Mixed into `TuiApp`."""

from __future__ import annotations

from rich.text import Text
from textual.screen import ModalScreen
from textual.widgets import Static

from drover.tui.restore_logic import unasked_stopped
from drover.tui.restore_stopped_dialog import RestoreStoppedDialog
from drover.tui.tui_state_helpers import ACCENT_CHIP, panes_of, state_glyph, worst_state

SEPARATOR = "  │  "


class StatusAndRestore:
    def update_status(self) -> None:
        tab = next((t for t in self.state["tabs"] if t["id"] == self.current_tab_id), None)
        text = Text()
        # Same colours as the app: done-green when linked to the daemon, blocked-orange while it reconnects.
        glyph, style = state_glyph("done" if self.connected else "blocked")
        text.append("● ", style=style)
        text.append("connected" if self.connected else "reconnecting…", style="dim" if self.connected else style)
        if tab:
            panes = panes_of(self.state, tab)
            glyph, style = state_glyph(worst_state([p["state"] for p in panes]))
            text.append(SEPARATOR, style="dim")
            text.append(f"{glyph} ", style=style)
            text.append(tab["name"], style="bold")
            if self.mode == "narrow" and len(panes) > 1:
                index = next((i for i, p in enumerate(panes) if p["id"] == self.focused_pane), 0) + 1
                text.append(f"  {index}/{len(panes)} panes", style="dim")
        if self.router.armed:
            text.append("  ")
            text.append(" PREFIX ", style=ACCENT_CHIP)
        view = self.layout_view.widget_for(self.focused_pane or "")
        if getattr(view, "scroll_mode", False):
            text.append("  ")
            text.append(f" SCROLL {view.emulator.scroll}/{view.emulator.history_size} ", style=ACCENT_CHIP)
            text.append("  ↑↓ PgUp/PgDn g/G move · y copy · q exit", style="dim")
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


