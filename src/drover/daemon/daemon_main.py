"""Daemon entry point: wire everything together and serve until stopped."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import signal
import sys

from aiohttp import web

from drover import __version__
from drover.app_paths import (
    bundled_rules_dir,
    daemon_info_file,
    log_dir,
    restrict_to_owner,
    session_file,
    state_dir,
    user_rules_dir,
)
from drover.chat.chat_manager import ChatManager
from drover.config.settings_loader import SettingsStore
from drover.core.event_hub import EventHub
from drover.core.git_watcher import GitWatcher
from drover.core.session_manager import SessionManager
from drover.core.session_persistence import SessionPersistence
from drover.core.state_store import StateStore
from drover.core.status_monitor import StatusMonitor
from drover.daemon.daemon_context import DaemonContext
from drover.daemon.web_server import build_app
from drover.notify.desktop_notifier_service import DesktopNotifierService
from drover.remote.remote_hub import RemoteHub

# Importing registers the RPC methods.
from drover.rpc import (  # noqa: F401
    methods_agent_input,
    methods_chat,
    methods_files,
    methods_git_fs,
    methods_layout,
    methods_panes,
    methods_system,
    methods_workspace,
)
from drover.status.detection_rule_loader import load_rule_sets

log = logging.getLogger("drover.daemon")


def build_context(token: str) -> DaemonContext:
    settings = SettingsStore()
    hub = EventHub()
    rule_sets, rule_errors = load_rule_sets(bundled_rules_dir(), user_rules_dir())
    manager = SessionManager(settings, hub, rule_sets)
    persistence = SessionPersistence(manager, StateStore(session_file()))
    notifier = DesktopNotifierService()
    monitor = StatusMonitor(manager, notifier)
    monitor.rule_errors = rule_errors
    ctx = DaemonContext(settings, hub, manager, persistence, monitor, notifier, token)
    ctx.remotes = RemoteHub(ctx)
    ctx.chats = ChatManager(state_dir() / "chats", hub.emit)
    manager.on_structure_change = persistence.schedule_save
    manager.notify_state = lambda name, kind, state: notifier.notify_state(name, kind, state, settings)
    return ctx


def _write_info_securely(path, info: dict) -> None:
    """Create daemon.json owner-only from the first byte (no world-readable window on POSIX)."""
    tmp = path.with_suffix(".tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(tmp, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(info, fh)
    restrict_to_owner(tmp)
    os.replace(tmp, path)


async def serve(host: str = "127.0.0.1", port: int = 0) -> None:
    from drover.daemon.daemon_client import is_alive, read_info

    if is_alive(read_info()):
        log.info("another drover daemon is already running; exiting")
        return
    ctx = build_context(secrets.token_urlsafe(32))
    ctx.persistence.load_previous()
    runner = web.AppRunner(build_app(ctx), access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", port)
    await site.start()
    ctx.port = site._server.sockets[0].getsockname()[1]  # actual port when 0 was requested
    if host not in ("127.0.0.1", "localhost", ""):
        # Extra, opt-in address (e.g. a Tailscale IP) so a phone can open the UI. Token still required.
        await web.TCPSite(runner, host, ctx.port).start()
    info = {"port": ctx.port, "token": ctx.token, "pid": os.getpid(), "version": __version__, "host": host}
    path = daemon_info_file()
    _write_info_securely(path, info)
    log.info("drover daemon %s listening on %s:%s", __version__, host, ctx.port)

    tasks = [asyncio.create_task(ctx.monitor.run()), asyncio.create_task(_housekeeping(ctx)),
             asyncio.create_task(GitWatcher(ctx.manager).run())]
    loop = asyncio.get_running_loop()
    if sys.platform != "win32":
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, ctx.request_stop)
    try:
        await ctx.stop_event.wait()
    finally:
        ctx.persistence.save_now()
        await ctx.chats.shutdown()
        for task in tasks:
            task.cancel()
        for link in ctx.remotes.links.values():
            link.stop()
        for pane in list(ctx.manager.panes.values()):
            pane.kill(wait=True)
        await runner.cleanup()
        try:
            if json.loads(path.read_text(encoding="utf-8")).get("pid") == os.getpid():
                path.unlink()
        except (OSError, ValueError):
            pass
        if ctx.restart:
            from drover.daemon.daemon_client import start_background

            start_background()  # runs the freshly installed bundle


async def _housekeeping(ctx: DaemonContext) -> None:
    while True:
        try:
            ctx.remotes.sync_from_file()
            ctx.persistence.save_now()
        except Exception:
            log.exception("housekeeping failed")
        await asyncio.sleep(30)


def main(host: str = "127.0.0.1", port: int = 0, foreground: bool = True) -> None:
    logging.basicConfig(
        level=logging.INFO if not os.environ.get("DROVER_DEBUG") else logging.DEBUG,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_dir() / "daemon.log", encoding="utf-8")]
        + ([logging.StreamHandler()] if foreground else []),
    )
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    try:
        from drover.legacy_herd_migration import migrate_autostart

        migrate_autostart()
    except OSError as exc:
        logging.getLogger(__name__).warning("could not migrate the old herd autostart entry: %s", exc)
    try:
        asyncio.run(serve(host, port))
    except KeyboardInterrupt:
        pass
