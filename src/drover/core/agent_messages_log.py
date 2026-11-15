"""In-memory log of agent-to-agent actions (spawn, wait, send, report) for the agent tree view."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict, dataclass, field

MAX_TEXT = 500


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
        # A long prompt would otherwise sit in memory in full and go out in every messages.list reply.
        message = AgentMessage(kind, source, target, text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "…")
        self.items.append(message)
        return message

    def add_state(self, pane_id: str, parent: str | None, state: str, text: str = "") -> AgentMessage | None:
        """A pane finished, exited or needs an answer: tell its parent, or you (target None) for an agent you started."""
        if state not in ("done", "blocked", "exited"):
            return None
        return self.add(state, pane_id, parent or None, text)

    def for_tree(self, pane_ids: set[str]) -> list[dict]:
        return [m.to_dict() for m in self.items if m.source in pane_ids or m.target in pane_ids]
