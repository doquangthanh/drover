"""Everything an RPC handler may need, in one object."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from drover.config.settings_loader import SettingsStore
from drover.core.event_hub import EventHub
from drover.core.session_manager import SessionManager
from drover.core.session_persistence import SessionPersistence
from drover.core.status_monitor import StatusMonitor
from drover.notify.desktop_notifier_service import DesktopNotifierService


@dataclass
class DaemonContext:
    settings: SettingsStore
    hub: EventHub
    manager: SessionManager
    persistence: SessionPersistence
    monitor: StatusMonitor
    notifier: DesktopNotifierService
    token: str
    port: int = 0
    started_at: float = field(default_factory=time.time)
    clients: dict[int, dict] = field(default_factory=dict)
    pending_answers: dict[str, tuple] = field(default_factory=dict)
    remotes: Any = None  # RemoteHub, set after construction
    chats: Any = None  # ChatManager, set after construction
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    restart: bool = False  # start a fresh daemon once this one has shut down (self-update)

    def request_stop(self) -> None:
        self.stop_event.set()

    def combined_state(self) -> dict:
        """Local snapshot plus every remote machine's snapshot (ids prefixed `alias:`)."""
        state = self.manager.snapshot()
        state["machines"] = self.remotes.public_state() if self.remotes else []
        state["chats"] = self.chats.snapshot() if self.chats else []
        state["prefix"] = self.settings.get("prefix", "C-a")
        state["tui_prefix"] = self.settings.get("tui_prefix", "C-b")
        state["theme"] = self.settings.get("theme", "dark")
        state["file_icons"] = self.settings.get("file_icons", "material")
        state["notify"] = self.settings.get("notify", {})
        state["orchestration"] = self.settings.get("orchestration", {})
        state["policy_pending"] = [
            {"id": k, "target": v[0], "text": v[1].strip(), "source": v[2]} for k, v in self.pending_answers.items()
        ]
        return state
