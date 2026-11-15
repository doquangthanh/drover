"""Native desktop notifications (Windows toast / notify-send / macOS) with quiet hours."""

from __future__ import annotations

import asyncio
import datetime as dt
import logging

log = logging.getLogger(__name__)

MESSAGES = {
    "blocked": "{name} is waiting for you",
    "done": "{name} finished",
    "exited": "{name} stopped",
}


def in_quiet_hours(spec: str, now: dt.time | None = None) -> bool:
    """`spec` like "23:00-07:00" (may wrap midnight). Empty = never quiet."""
    if not spec or "-" not in spec:
        return False
    try:
        start_s, end_s = (part.strip() for part in spec.split("-", 1))
        start = dt.time.fromisoformat(start_s)
        end = dt.time.fromisoformat(end_s)
    except ValueError:
        return False
    now = now or dt.datetime.now().time()
    if start <= end:
        return start <= now < end
    return now >= start or now < end


class DesktopNotifierService:
    def __init__(self) -> None:
        self._notifier = None
        self.enabled = True
        self._tasks: set = set()
        try:
            from desktop_notifier import DesktopNotifier

            self._notifier = DesktopNotifier(app_name="drover")
        except Exception as exc:  # missing platform support must never break the daemon
            log.info("desktop notifications unavailable: %s", exc)

    def notify_state(self, name: str, kind: str, state: str, settings) -> None:
        if state not in MESSAGES or not self.enabled:
            return
        channels = settings.get(f"notify.{state}", []) or []
        if "desktop" not in channels:
            return
        if in_quiet_hours(settings.get("notify.quiet_hours", "")):
            return
        title = MESSAGES[state].format(name=name)
        self.send(title, kind, sound="sound" in channels)

    def send(self, title: str, body: str, sound: bool = False) -> None:
        if self._notifier is None:
            return
        try:
            from desktop_notifier import DEFAULT_SOUND

            coro = self._notifier.send(title=title, message=body, sound=DEFAULT_SOUND if sound else None)
            task = asyncio.get_running_loop().create_task(self._safe(coro))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        except Exception as exc:
            log.debug("notification failed: %s", exc)

    @staticmethod
    async def _safe(coro) -> None:
        try:
            await coro
        except Exception as exc:
            log.debug("notification failed: %s", exc)
