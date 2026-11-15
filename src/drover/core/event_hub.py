"""Fan-out of daemon events to connected clients (UI websockets, CLI waiters, remote hub)."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)

Listener = Callable[[str, Any], None]


class EventHub:
    def __init__(self) -> None:
        self._listeners: set[Listener] = set()

    def subscribe(self, listener: Listener) -> Callable[[], None]:
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def emit(self, name: str, data: Any) -> None:
        for listener in list(self._listeners):
            try:
                listener(name, data)
            except Exception:
                log.exception("event listener failed for %s", name)


class BoundedQueue:
    """Per-client outbound queue.

    When a slow client falls behind, droppable traffic (output, events) is discarded and the client is
    told to resync (re-fetch state and re-attach panes, which replays their output). RPC replies are
    never dropped, so no request is left hanging.
    """

    def __init__(self, maxsize: int = 2000) -> None:
        self.maxsize = maxsize
        self.items: deque = deque()
        self.ready = asyncio.Event()
        self.overflowed = False

    def put(self, item: Any) -> None:
        important = isinstance(item, dict) and item.get("t") == "res"
        if self.overflowed and not important:
            return
        if not important and len(self.items) >= self.maxsize:
            self.overflowed = True
            self.items = deque(i for i in self.items if isinstance(i, dict) and i.get("t") == "res")
            self.items.append({"t": "resync"})
        else:
            self.items.append(item)
        self.ready.set()

    async def get(self) -> Any:
        while not self.items:
            self.ready.clear()
            await self.ready.wait()
        item = self.items.popleft()
        if isinstance(item, dict) and item.get("t") == "resync":
            self.overflowed = False
        return item
