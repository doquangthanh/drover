"""Save the workspace to disk and bring it back after a daemon/computer restart."""

from __future__ import annotations

import asyncio
import time

from herd.core import split_layout_tree as layout
from herd.core.session_manager import SessionManager
from herd.core.state_store import StateStore
from herd.core.workspace_models import Space, Tab, bump_id_counter


class SessionPersistence:
    def __init__(self, manager: SessionManager, store: StateStore) -> None:
        self.manager = manager
        self.store = store
        self._pending: asyncio.TimerHandle | None = None

    def serialize(self) -> dict:
        m = self.manager
        panes = []
        for pane in m.panes.values():
            meta = pane.meta
            panes.append({"id": meta.id, "name": meta.name, "kind": meta.kind, "command": meta.command,
                          "cwd": meta.cwd, "space_id": meta.space_id, "tab_id": meta.tab_id,
                          "parent": meta.parent, "resume": meta.resume})
        return {"version": 1, "saved_at": time.time(),
                "spaces": [s.to_dict() for s in m.spaces.values()],
                "tabs": [t.to_dict() for t in m.tabs.values()],
                "panes": panes + m.stopped}

    def schedule_save(self) -> None:
        loop = asyncio.get_running_loop()
        if self._pending:
            self._pending.cancel()
        self._pending = loop.call_later(1.0, self.save_now)

    def save_now(self) -> None:
        self._pending = None
        self.store.save(self.serialize())

    def load_previous(self) -> None:
        """Recreate spaces and tabs; previous panes become `stopped` entries awaiting resume."""
        data = self.store.load()
        if not data:
            return
        m = self.manager
        for raw in data.get("spaces", []):
            m.spaces[raw["id"]] = Space(**raw)
        for raw in data.get("tabs", []):
            tab = Tab(**{k: raw.get(k) for k in ("id", "space_id", "name", "layout", "focused")})
            if layout.is_valid(tab.layout):
                m.tabs[tab.id] = tab
        m.stopped = [p for p in data.get("panes", []) if p.get("tab_id") in m.tabs]
        known = {p["id"] for p in m.stopped}
        for tab in list(m.tabs.values()):
            for pane_id in layout.pane_ids(tab.layout):
                if pane_id not in known:
                    tab.layout = layout.remove(tab.layout, pane_id)
            if not tab.layout:
                m.tabs.pop(tab.id)
        bump_id_counter(list(m.spaces) + list(m.tabs) + list(known))

    def resume(self, pane_ids: list[str], use_resume_command: bool = True) -> list[str]:
        m = self.manager
        started = []
        for old in [p for p in m.stopped if p["id"] in pane_ids]:
            command = (old.get("resume") if use_resume_command else "") or old.get("command", "")
            if old.get("kind") == "shell":
                command = ""
            pane = m.create_pane(command, old["cwd"], old["name"], tab_id=old["tab_id"], split_from=old["id"])
            tab = m.tabs[old["tab_id"]]
            tab.layout = layout.remove(tab.layout, old["id"])
            tab.focused = pane.meta.id
            m.stopped.remove(old)
            started.append(pane.meta.id)
        m._changed()
        return started

    def discard(self, pane_ids: list[str] | None = None) -> None:
        m = self.manager
        drop = [p for p in m.stopped if pane_ids is None or p["id"] in pane_ids]
        for old in drop:
            tab = m.tabs.get(old["tab_id"])
            if tab:
                tab.layout = layout.remove(tab.layout, old["id"])
                if not tab.layout:
                    m.tabs.pop(tab.id)
            m.stopped.remove(old)
        m._changed()
