"""Manages links to all remote machines and routes client traffic to the right one."""

from __future__ import annotations

import glob
import logging
from pathlib import Path

from herd.remote.machine_registry import Machine, load_machines, machines_file, save_machines, validate_new
from herd.remote.remote_link import RemoteLink
from herd.rpc.rpc_registry import E_BAD_PARAMS, E_NOT_FOUND, RpcError, need, registry

log = logging.getLogger(__name__)


class RemoteHub:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.links: dict[str, RemoteLink] = {}
        self._mtime = None

    def _emit(self, name: str, data) -> None:
        if name in ("state", "machines"):
            self.ctx.hub.emit("state", None)
            return
        self.ctx.hub.emit(name, data)
        if name == "status" and data:
            pane = data.get("pane", {})
            self.ctx.notifier.notify_state(pane.get("name", "agent"), pane.get("kind", ""), data.get("new"),
                                           self.ctx.settings)

    def sync_from_file(self) -> None:
        """Start/stop links to match machines.toml (polled by the daemon)."""
        try:
            mtime = machines_file().stat().st_mtime
        except OSError:
            mtime = None
        if mtime == self._mtime:
            return
        self._mtime = mtime
        wanted = load_machines()
        for alias in list(self.links):
            if alias not in wanted or wanted[alias] != self.links[alias].machine:
                self.links.pop(alias).stop()
        for alias, machine in wanted.items():
            if alias not in self.links:
                link = RemoteLink(machine, self._emit)
                self.links[alias] = link
                link.start()
        self.ctx.hub.emit("state", None)

    def owns(self, value: str) -> bool:
        if not value:
            return False
        alias = value.split(":", 1)[0]
        return alias in self.links and (value == alias or value.startswith(alias + ":"))

    async def forward_from_client(self, session, msg: dict) -> None:
        value = str(msg.pop("_route", "") or msg.get("pane") or "")
        alias = value.split(":", 1)[0]
        await self.links[alias].forward(session, msg)

    def public_state(self) -> list[dict]:
        return [link.public() for link in self.links.values()]


def _local_wheel() -> str | None:
    root = Path(__file__).resolve().parents[3]
    wheels = sorted(glob.glob(str(root / "dist" / "herd-*.whl")))
    return wheels[-1] if wheels else None


@registry.method("machine.list", "Remote machines and their connection state", "")
async def machine_list(ctx, p: dict) -> list:
    return ctx.remotes.public_state()


@registry.method("machine.add", "Add a machine to machines.toml", "alias, target, port?, key?, install?")
async def machine_add(ctx, p: dict) -> dict:
    machines = load_machines()
    alias, target = need(p, "alias"), need(p, "target")
    try:
        validate_new(alias, target, machines)
    except ValueError as exc:
        raise RpcError(E_BAD_PARAMS, str(exc)) from exc
    machine = Machine(alias=alias, target=target, port=int(p.get("port") or 22), key=str(p.get("key") or ""))
    if p.get("install"):
        await install_on(machine)
    machines[alias] = machine
    save_machines(machines)
    ctx.remotes.sync_from_file()
    return {"alias": alias}


async def install_on(machine: Machine) -> None:
    import asyncssh

    from herd.remote.remote_bootstrap import BootstrapError, install_hd

    user, host = machine.user_host
    try:
        async with asyncssh.connect(host, username=user, port=machine.port,
                                    client_keys=[machine.key] if machine.key else ()) as conn:
            await install_hd(conn, _local_wheel(), lambda step: log.info("install %s: %s", machine.alias, step))
    except (BootstrapError, OSError, asyncssh.Error) as exc:
        raise RpcError(1, f"install on {machine.alias} failed: {exc}") from exc


@registry.method("machine.remove", "Forget a machine (its agents keep running there)", "alias")
async def machine_remove(ctx, p: dict) -> None:
    machines = load_machines()
    if machines.pop(need(p, "alias"), None) is None:
        raise RpcError(E_NOT_FOUND, "no such machine")
    save_machines(machines)
    ctx.remotes.sync_from_file()


@registry.method("machine.test", "Try SSH + remote hd without saving", "target, port?, key?")
async def machine_test(ctx, p: dict) -> dict:
    import asyncssh

    from herd.remote.remote_bootstrap import ensure_remote_daemon

    machine = Machine(alias="test", target=need(p, "target"), port=int(p.get("port") or 22), key=p.get("key", ""))
    user, host = machine.user_host
    steps = []
    try:
        async with asyncssh.connect(host, username=user, port=machine.port,
                                    client_keys=[machine.key] if machine.key else ()) as conn:
            steps.append("ssh ok")
            info = await ensure_remote_daemon(conn)
            steps.append(f"hd {info.get('version') or ''} running")
    except Exception as exc:
        return {"ok": False, "steps": steps, "error": str(exc)}
    return {"ok": True, "steps": steps}
