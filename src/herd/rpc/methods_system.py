"""RPC methods for the server itself, detection rules and config files."""

from __future__ import annotations

import asyncio
import os
import sys
import time

from herd import __version__
from herd.app_paths import config_dir
from herd.core import self_update
from herd.rpc.rpc_registry import E_BAD_PARAMS, RpcError, need, registry
from herd.rpc.target_resolver import resolve_pane
from herd.skill.agent_skill_text import AGENT_SKILL
from herd.status.status_detector import evaluate

CONFIG_FILES = ("settings.toml", "keys.toml", "machines.toml", "AGENTS.md")


@registry.method("server.info", "Version, pid, port, uptime, clients", "")
async def server_info(ctx, p: dict) -> dict:
    counts: dict[str, int] = {}
    for pane in ctx.manager.panes.values():
        counts[pane.state] = counts.get(pane.state, 0) + 1
    return {
        "version": __version__, "pid": os.getpid(), "port": ctx.port, "platform": sys.platform,
        "started_at": ctx.started_at, "uptime": time.time() - ctx.started_at,
        "clients": list(ctx.clients.values()), "counts": counts,
        "config_dir": str(config_dir()), "session_saved": ctx.persistence.store.path.exists(),
        "rule_errors": ctx.monitor.rule_errors, "settings_errors": ctx.settings.errors,
    }


@registry.method("server.stop", "Save state and stop the daemon", "")
async def server_stop(ctx, p: dict) -> None:
    ctx.persistence.save_now()
    asyncio.get_running_loop().call_later(0.2, ctx.request_stop)


@registry.method("update.check", "Is a newer release on GitHub?", "")
async def update_check(ctx, p: dict) -> dict:
    try:
        return await asyncio.to_thread(self_update.check)
    except self_update.UpdateError as exc:
        raise RpcError(E_BAD_PARAMS, str(exc)) from exc


@registry.method("update.apply", "Download a release, replace this install and restart the daemon", "tag")
async def update_apply(ctx, p: dict) -> None:
    try:
        await asyncio.to_thread(self_update.apply, need(p, "tag"))
    except self_update.UpdateError as exc:
        raise RpcError(E_BAD_PARAMS, str(exc)) from exc
    ctx.restart = True  # open windows follow the new daemon (follow_daemon)
    ctx.persistence.save_now()
    asyncio.get_running_loop().call_later(0.5, ctx.request_stop)


@registry.method("schema", "This API as OpenRPC-style JSON", "")
async def schema(ctx, p: dict) -> dict:
    return registry.schema()


@registry.method("skill.text", "Instructions that teach an agent to use hd", "")
async def skill_text(ctx, p: dict) -> dict:
    return {"text": AGENT_SKILL}


@registry.method("rules.list", "Loaded detection rule sets", "")
async def rules_list(ctx, p: dict) -> list:
    return [{"id": r.id, "aliases": r.aliases, "source": r.source, "path": r.path, "resume": r.resume,
             "rules": len(r.rules)} for r in ctx.manager.rule_sets.values()]


@registry.method("rules.test", "Run detection rules against a pane and explain the result", "pane, kind?")
async def rules_test(ctx, p: dict) -> dict:
    pane = ctx.manager.get(resolve_pane(ctx.manager, need(p, "pane"), p.get("caller")))
    kind = p.get("kind") or pane.meta.kind
    pane.flush_screen()
    lines = pane.screen.visible_lines()
    winner, results = evaluate(ctx.manager.rule_sets.get(kind), pane.screen.title, lines)
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    return {"pane": pane.meta.id, "kind": kind, "title": pane.screen.title, "state": pane.state,
            "detected": winner, "screen": lines[-20:],
            "results": [r.__dict__ for r in results],
            "osc7501": pane.tracker.reported}


@registry.method("settings.files", "Config files with their contents", "")
async def settings_files(ctx, p: dict) -> dict:
    base = config_dir()
    files = []
    for name in CONFIG_FILES:
        path = base / name
        files.append({"name": name, "path": str(path), "exists": path.exists(),
                      "text": path.read_text(encoding="utf-8")[:50_000] if path.exists() else ""})
    for path in sorted((base / "rules").glob("*.toml")):
        files.append({"name": f"rules/{path.name}", "path": str(path), "exists": True,
                      "text": path.read_text(encoding="utf-8")[:50_000]})
    return {"dir": str(base), "files": files, "errors": ctx.settings.errors + ctx.monitor.rule_errors}


@registry.method("settings.write", "Save a config file (validated TOML)", "name, text")
async def settings_write(ctx, p: dict) -> None:
    import tomllib

    name, text = need(p, "name"), str(p.get("text", ""))
    allowed = set(CONFIG_FILES) | {f"rules/{x.name}" for x in (config_dir() / "rules").glob("*.toml")}
    if name not in allowed and not (name.startswith("rules/") and name.endswith(".toml") and "/" not in name[6:]
                                    and ".." not in name):
        raise RpcError(E_BAD_PARAMS, "unknown config file")
    if name.endswith(".toml"):
        try:
            tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise RpcError(E_BAD_PARAMS, f"invalid TOML: {exc}") from exc
    path = config_dir() / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@registry.method("notify.test", "Send a test desktop notification", "")
async def notify_test(ctx, p: dict) -> None:
    ctx.notifier.send("herd notifications work", "You'll see this when an agent needs you.", sound=True)
