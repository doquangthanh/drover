"""Background loop: run detection rules on panes, publish state changes, trigger notifications."""

from __future__ import annotations

import asyncio
import logging
import time

from drover.app_paths import bundled_rules_dir, user_rules_dir
from drover.core.foreground_process_probe import foreground_agent_kind, foreground_pgid
from drover.core.session_manager import SessionManager
from drover.notify.desktop_notifier_service import DesktopNotifierService
from drover.status.detection_rule_loader import load_rule_sets
from drover.status.status_detector import detect_kind_from_title, evaluate

log = logging.getLogger(__name__)
TICK = 0.25


class StatusMonitor:
    def __init__(self, manager: SessionManager, notifier: DesktopNotifierService) -> None:
        self.manager = manager
        self.notifier = notifier
        self.rule_errors: list[str] = []
        self._rules_stamp = None

    async def run(self) -> None:
        last_config_check = 0.0
        while True:
            try:
                now = time.time()
                if now - last_config_check > 2:
                    last_config_check = now
                    self.reload_config()
                    self.manager.follow_space_folders()
                for pane in list(self.manager.panes.values()):
                    self.probe_foreground(pane, now)
                    self.check_pane(pane, now)
            except Exception:
                log.exception("status monitor tick failed")
            await asyncio.sleep(TICK)

    def reload_config(self) -> None:
        self.manager.settings.reload_if_changed()
        user_dir = user_rules_dir()
        stamp = tuple(sorted((p.name, p.stat().st_mtime) for p in user_dir.glob("*.toml")))
        if stamp != self._rules_stamp:
            self._rules_stamp = stamp
            sets, errors = load_rule_sets(bundled_rules_dir(), user_dir)
            self.manager.rule_sets.clear()
            self.manager.rule_sets.update(sets)
            self.rule_errors = errors

    def probe_foreground(self, pane, now: float) -> None:
        """Herdr-style: a shell pane is an agent while that agent holds its terminal (Linux/macOS)."""
        b = pane.backend
        if not pane.shell_launched or not b or b.tty_fd is None or not pane.alive:
            return
        pgid = foreground_pgid(b.pid, b.tty_fd)
        if pgid is None or (pgid == pane.fg_pgid and now - pane.fg_checked_at < 5):
            return
        pane.fg_pgid, pane.fg_checked_at = pgid, now
        kinds = set(self.manager.rule_sets)
        kind = "shell" if pgid == b.pid else (foreground_agent_kind(pgid, kinds) or "shell")
        self.manager.set_pane_kind(pane, kind)

    def check_pane(self, pane, now: float) -> None:
        recent = now - pane.last_output_at < 3
        # New input holds "working" for a few seconds; a quick command can go quiet before the hold ends, so keep
        # evaluating until the idle candidate has had time to debounce, or the pane stays "working" forever.
        settling = now < pane.tracker.hold_until + 1.5
        if pane.read_lock.locked() or now < pane.detection_paused_until:
            return  # `dr read` is scrolling the agent: its redraws are ours, not the agent working

        if not (pane.dirty or recent or settling or pane.tracker._candidate != pane.tracker.state):
            return
        pane.dirty = False
        title_fallback = pane.backend is None or pane.backend.tty_fd is None  # Windows: no process groups
        if title_fallback and pane.meta.kind == "shell" and pane.screen.title:
            guessed = detect_kind_from_title(pane.screen.title, self.manager.rule_sets)
            if guessed and guessed != "shell":
                pane.meta.kind = guessed
                pane.meta.resume = self.manager.rule_sets[guessed].resume  # so a restart can resume it
        rule_set = self.manager.rule_sets.get(pane.meta.kind)
        detected, _ = evaluate(rule_set, pane.screen.title, pane.screen.visible_lines())
        old = pane.state
        # Shells go idle after every command; only agents get a "done" (and its notification).
        # Start-up output (banner, spinner while loading) is not "finished work" either.
        worked_after_boot = pane.tracker.since - pane.meta.created_at > 4
        allow_done = pane.meta.kind != "shell" and worked_after_boot
        new = pane.tracker.observe(detected, pane.last_output_at, pane.focused, now, allow_done=allow_done)
        if new is None:
            return
        if new in ("blocked", "done") and not pane.focused:
            pane.unread = True
        # A focused agent finishing its turn goes working -> idle (no "done" badge), but it did finish: log it.
        finished = allow_done and old == "working" and new == "idle"
        self.manager.messages.add_state(pane.meta.id, pane.meta.parent, "done" if finished else new)
        self.manager.hub.emit("pane", pane.to_dict())
        self.manager.hub.emit("status", {"pane": pane.to_dict(), "old": old, "new": new})
        if not pane.focused:
            self.notifier.notify_state(pane.meta.name, pane.meta.kind, new, self.manager.settings,
                                       detail=pane.screen.title)
