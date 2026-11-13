"""Everything an RPC handler may need, in one object."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from herd.config.settings_loader import SettingsStore
from herd.core.event_hub import EventHub
from herd.core.session_manager import SessionManager
from herd.core.session_persistence import SessionPersistence
from herd.core.status_monitor import StatusMonitor
from herd.notify.desktop_notifier_service import DesktopNotifierService


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
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)

    def request_stop(self) -> None:
        self.stop_event.set()

    def combined_state(self) -> dict:
        """Local snapshot plus every remote machine's snapshot (ids prefixed `alias:`)."""
        state = self.manager.snapshot()
        state["machines"] = self.remotes.public_state() if self.remotes else []
        state["prefix"] = self.settings.get("prefix", "C-b")
        state["policy_pending"] = [
            {"id": k, "target": v[0], "text": v[1].strip(), "source": v[2]} for k, v in self.pending_answers.items()
        ]
        return state
