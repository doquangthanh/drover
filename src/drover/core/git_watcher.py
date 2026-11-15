"""Keeps each space's git branch / change count fresh so the UI can show it (status bar, sidebar, phone)."""

from __future__ import annotations

import asyncio
import logging

from drover.core.session_manager import SessionManager
from drover.git import worktree_service as wt

log = logging.getLogger(__name__)
INTERVAL = 5.0  # one `git status` per space every few seconds; agents commit and switch branches all the time


class GitWatcher:
    def __init__(self, manager: SessionManager) -> None:
        self.manager = manager

    async def refresh_once(self) -> bool:
        """Re-read every space. Returns True (and pushes state to the UI) when anything changed."""
        spaces = list(self.manager.spaces.values())
        results = await asyncio.gather(*(wt.quick_status(s.cwd) for s in spaces), return_exceptions=True)
        fresh = {s.id: r for s, r in zip(spaces, results) if isinstance(r, dict)}
        if fresh == self.manager.git:
            return False
        self.manager.git = fresh
        self.manager._changed()
        return True

    async def run(self) -> None:
        while True:
            try:
                await self.refresh_once()
            except Exception:
                log.exception("git watcher tick failed")
            await asyncio.sleep(INTERVAL)
