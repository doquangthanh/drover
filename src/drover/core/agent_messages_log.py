"""In-memory log of agent-to-agent actions (spawn, wait, send, report) for the agent tree view."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict, dataclass, field


@dataclass
class AgentMessage:
    kind: str  # spawn | wait | send | read | done | denied
    source: str | None  # pane id of the acting agent, None = user / CLI outside drover
    target: str | None
    text: str = ""
    at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


class AgentMessagesLog:
    def __init__(self, limit: int = 500) -> None:
        self.items: deque[AgentMessage] = deque(maxlen=limit)

    def add(self, kind: str, source: str | None, target: str | None, text: str = "") -> AgentMessage:
        message = AgentMessage(kind, source, target, text)
        self.items.append(message)
        return message

    def for_tree(self, pane_ids: set[str]) -> list[dict]:
        return [m.to_dict() for m in self.items if m.source in pane_ids or m.target in pane_ids]
