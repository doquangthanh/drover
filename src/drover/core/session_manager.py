"""Owns spaces, tabs and panes on this machine. All mutations go through here."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from drover.config.settings_loader import SettingsStore
from drover.core import split_layout_tree as layout
from drover.core.agent_messages_log import AgentMessagesLog
from drover.core.event_hub import EventHub
from drover.core.orchestration_policy import OrchestrationPolicy, PolicyError
from drover.core.pane_session import PaneMeta, PaneSession
from drover.core.workspace_models import Space, Tab, new_id
from drover.pty.pty_backend_factory import default_shell, resolve_argv, split_command
from drover.self_command import pane_path
from drover.status.detection_rule_loader import AgentRuleSet, match_agent_kind


class SessionManager:
    def __init__(self, settings: SettingsStore, hub: EventHub, rule_sets: dict[str, AgentRuleSet]) -> None:
        self.settings = settings
        self.hub = hub
        self.rule_sets = rule_sets
        self.spaces: dict[str, Space] = {}
        self.tabs: dict[str, Tab] = {}
        self.panes: dict[str, PaneSession] = {}
        self.stopped: list[dict] = []  # panes from a previous run, offered for resume
        self.git: dict[str, dict] = {}  # space id -> {branch, dirty, ahead}, refreshed by GitWatcher
        self.messages = AgentMessagesLog()
        self.on_structure_change = lambda: None
        self.notify_state = lambda name, kind, state, detail="": None  # wired to desktop notifications by the daemon

    # -- spaces & tabs ---------------------------------------------------------------
    def ensure_space(self, cwd: str) -> Space:
        norm = os.path.normcase(str(Path(cwd).resolve()))
        for space in self.spaces.values():
            if os.path.normcase(str(Path(space.cwd).resolve())) == norm:
                return space
        space = Space.for_folder(str(Path(cwd).resolve()), color=len(self.spaces) % 8)
        self.spaces[space.id] = space
        return space

    def create_tab(self, space_id: str, name: str) -> Tab:
        tab = Tab(id=new_id("t"), space_id=space_id, name=name)
        self.tabs[tab.id] = tab
        return tab

    def remove_space(self, space_id: str) -> None:
        for tab in [t for t in self.tabs.values() if t.space_id == space_id]:
            for pane_id in layout.pane_ids(tab.layout):
                if pane_id in self.panes:
                    self.close_pane(pane_id, notify=False)
            self.tabs.pop(tab.id, None)
        # Panes from a previous run in this space are not live: just forget them.
        self.stopped = [s for s in self.stopped if s.get("space_id") != space_id]
        self.spaces.pop(space_id, None)
        self._changed()

    # -- panes -----------------------------------------------------------------------
    def depth_of(self, pane_id: str | None) -> int | None:
        depth, seen = None, set()
        while pane_id and pane_id in self.panes and pane_id not in seen:
            seen.add(pane_id)
            depth = (depth or 0) + 1
            pane_id = self.panes[pane_id].meta.parent
        return depth

    def create_pane(self, command: str = "", cwd: str = "", name: str = "", *, tab_id: str | None = None,
                    split_from: str | None = None, direction: str = "row", parent: str | None = None,
                    cols: int = 120, rows: int = 32) -> PaneSession:
        policy = OrchestrationPolicy.from_settings(self.settings.get("orchestration", {}))
        live = sum(1 for p in self.panes.values() if p.alive)
        policy.check_spawn(live, self.depth_of(parent) if parent else None)
        cwd = cwd or (self.panes[parent].meta.cwd if parent in self.panes else str(Path.home()))
        if not Path(cwd).is_dir():
            raise ValueError(f"folder does not exist: {cwd}")
        argv = split_command(command) if command.strip() else default_shell(self.settings.get("shell", ""))
        kind = match_agent_kind(command, self.rule_sets) if command.strip() else "shell"
        name = name or self._default_name(kind)
        pane_id = new_id("%")
        rule_set = self.rule_sets.get(kind)
        meta = PaneMeta(id=pane_id, name=name, kind=kind, command=command or " ".join(argv), argv=argv,
                        cwd=cwd, space_id="", tab_id="", parent=parent,
                        resume=rule_set.resume if rule_set else "")
        pane = PaneSession(meta, cols, rows, int(self.settings.get("scrollback", 5000)))
        pane.on_exit_hook = self._on_pane_exit
        env = {**os.environ, "TERM": "xterm-256color", "COLORTERM": "truecolor",
               "DR_PANE_ID": pane_id, "DROVER": "1", "PATH": pane_path(os.environ.get("PATH", ""))}
        pane.start(resolve_argv(argv), env)  # may raise: create no space/tab before this succeeds
        if tab_id and tab_id in self.tabs:
            tab = self.tabs[tab_id]
        else:
            tab = self.create_tab(self.ensure_space(cwd).id, name)
        meta.space_id, meta.tab_id = tab.space_id, tab.id
        self.panes[pane_id] = pane
        tab.layout = layout.insert(tab.layout, split_from or tab.focused, pane_id, direction)
        tab.focused = pane_id
        # parent None = started by you (UI / CLI), so every agent gets a lane on the Flow board.
        self.messages.add("spawn", parent or None, pane_id, meta.command)
        self._changed()
        return pane

    def _default_name(self, kind: str) -> str:
        taken = {p.meta.name for p in self.panes.values()}
        for n in range(1, 1000):
            candidate = kind if n == 1 else f"{kind}-{n}"
            if candidate not in taken:
                return candidate
        return kind

    def _on_pane_exit(self, pane: PaneSession) -> None:
        # A one-shot helper (`dr run claude -p ...`) exits instead of going "done": still report it on the Flow board.
        self.messages.add_state(pane.meta.id, pane.meta.parent, "exited", f"exit code {pane.exit_code}")
        self.hub.emit("pane", pane.to_dict())
        self.hub.emit("status", {"pane": pane.to_dict(), "old": "working", "new": "exited"})
        if not pane.focused:
            self.notify_state(pane.meta.name, pane.meta.kind, "exited", pane.screen.title)
        if self.settings.get("orchestration.kill_children_on_parent_exit", False):
            for child in self.children_of(pane.meta.id):
                if child in self.panes:
                    self.panes[child].kill()
        self._changed()

    def close_pane(self, pane_id: str, notify: bool = True) -> None:
        pane = self.panes.pop(pane_id, None)
        if not pane:
            raise KeyError(pane_id)
        pane.kill()
        self.detach_from_tab(pane)
        if notify:
            self._changed()

    def detach_from_tab(self, pane: PaneSession) -> None:
        """Take a pane out of its tab's layout; a tab left empty is removed."""
        tab = self.tabs.get(pane.meta.tab_id)
        if not tab:
            return
        tab.layout = layout.remove(tab.layout, pane.meta.id)
        if tab.focused == pane.meta.id:
            ids = layout.pane_ids(tab.layout)
            tab.focused = ids[-1] if ids else None
            tab.zoomed = False  # the zoom belonged to the pane that left
        if not tab.layout:
            self.tabs.pop(tab.id, None)

    def get(self, pane_id: str) -> PaneSession:
        if pane_id not in self.panes:
            raise KeyError(f"no pane {pane_id}")
        return self.panes[pane_id]

    def focus(self, pane_id: str) -> None:
        for pane in self.panes.values():
            pane.focused = pane.meta.id == pane_id
        pane = self.get(pane_id)
        pane.unread = False
        tab = self.tabs.get(pane.meta.tab_id)
        if tab:
            tab.focused = pane_id
        pane.tracker.acknowledge()
        self.hub.emit("pane", pane.to_dict())

    def children_of(self, pane_id: str) -> list[str]:
        return [p.meta.id for p in self.panes.values() if p.meta.parent == pane_id]

    # -- snapshot ----------------------------------------------------------------------
    def snapshot(self) -> dict[str, Any]:
        return {
            "spaces": [{**s.to_dict(), **self.git.get(s.id, {})} for s in self.spaces.values()],
            "tabs": [t.to_dict() for t in self.tabs.values()],
            "panes": [p.to_dict() for p in self.panes.values()],
            "stopped": self.stopped,
        }

    def _changed(self) -> None:
        self.hub.emit("state", self.snapshot())
        self.on_structure_change()


__all__ = ["PolicyError", "SessionManager"]
