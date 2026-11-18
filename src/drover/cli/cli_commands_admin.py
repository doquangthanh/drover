"""dr status / schema / skill / server / machine / worktree / rules."""

from __future__ import annotations

import json
import os
import sys

from drover.app_paths import log_dir
from drover.daemon import daemon_client as dc


def add_admin_parsers(sub) -> None:
    server = sub.add_parser("server", help="start | stop | restart | run | ensure | logs | autostart")
    server.add_argument("action", choices=["start", "stop", "restart", "run", "ensure", "logs", "autostart", "url"])
    server.add_argument("value", nargs="?", default="", help="for autostart: on | off")
    server.add_argument("--json", action="store_true")
    server.add_argument("--background", action="store_true", help=argparse_hidden())
    server.add_argument("--listen", default="127.0.0.1", help="bind address (e.g. a Tailscale IP for phone)")

    machine = sub.add_parser("machine", help="add | ls | rm | test remote machines")
    machine.add_argument("action", choices=["add", "ls", "rm", "test"])
    machine.add_argument("alias", nargs="?", default="")
    machine.add_argument("target", nargs="?", default="")
    machine.add_argument("--port", type=int, default=22)
    machine.add_argument("--key", default="")
    machine.add_argument("--install", action="store_true", help="install dr on the machine first")

    worktree = sub.add_parser("worktree", help="new | ls | rm task worktrees")
    worktree.add_argument("action", choices=["new", "ls", "rm"])
    worktree.add_argument("name", nargs="?", default="", help="task name (new) or path (rm)")
    worktree.add_argument("--repo", default="")
    worktree.add_argument("--base", default="")
    worktree.add_argument("--run", default="", help="start this agent in the new worktree")
    worktree.add_argument("--force", action="store_true")

    rules = sub.add_parser("rules", help="test | ls detection rules")
    rules.add_argument("action", choices=["test", "ls"])
    rules.add_argument("target", nargs="?", default="")
    rules.add_argument("--kind", default="")


def argparse_hidden() -> str:
    import argparse

    return argparse.SUPPRESS


def cmd_status(args) -> int:
    info = dc.call("server.info")
    counts = info["counts"]
    total = sum(counts.values())
    machines = dc.call("machine.list")
    up = 1 + sum(1 for m in machines if m["status"] == "connected")
    print(f"server up · dr {info['version']} · pid {info['pid']} · port {info['port']}")
    print(f"{up} of {1 + len(machines)} machines · {total} local agents "
          f"({counts.get('blocked', 0)} need you, {counts.get('done', 0)} done, "
          f"{counts.get('working', 0)} working)")
    for m in machines:
        print(f"  {m['alias']:<12} {m['status']:<11} {m.get('latency_ms') or '-'} ms  {m['error']}")
    return 0


def cmd_schema(args) -> int:
    print(json.dumps(dc.call("schema"), indent=1))
    return 0


def cmd_skill(args) -> int:
    from drover.skill.agent_skill_text import AGENT_SKILL

    print(AGENT_SKILL)
    return 0


def _bundled_rust_daemon() -> str | None:
    """`drover-server` next to a packaged Linux `dr`, unless DROVER_ENGINE=python asks for the Python daemon."""
    from drover.self_command import bundle_dir, is_frozen

    if not is_frozen() or sys.platform == "win32" or os.environ.get("DROVER_ENGINE") == "python":
        return None
    exe = bundle_dir() / "drover-server"
    return str(exe) if exe.is_file() and os.access(exe, os.X_OK) else None


def cmd_server(args) -> int:
    action = args.action
    if action == "run":
        rust_daemon = _bundled_rust_daemon()
        if rust_daemon:  # release bundle: the daemon is the Rust drover-server next to dr
            os.execv(rust_daemon, [rust_daemon, "server", "run", "--listen", args.listen]
                     + (["--background"] if args.background else []))
        from drover.daemon.daemon_main import main as run_daemon

        if args.listen in ("0.0.0.0", "::", "*"):
            print("error: refusing to listen on every network interface. Give one address you trust, "
                  "e.g. your Tailscale IP (100.x.y.z).", file=sys.stderr)
            return 5
        if args.listen not in ("127.0.0.1", "localhost") and not args.listen.startswith("100."):
            print("warning: the UI token travels over plain HTTP; use this only on a private network "
                  "such as Tailscale.", file=sys.stderr)

        run_daemon(host=args.listen, foreground=not args.background)
        return 0
    if action in ("start", "ensure"):
        info = dc.ensure_daemon()
        if args.json:
            print(json.dumps({"port": info["port"], "token": info["token"], "version": info.get("version")}))
        else:
            print(f"drover daemon running on port {info['port']} (pid {info['pid']})")
        return 0
    if action == "stop":
        if dc.is_alive(dc.read_info()):
            dc.call("server.stop", autostart=False)
            print("stopped")
        return 0
    if action == "restart":
        import time

        old = dc.read_info()
        if dc.is_alive(old):
            dc.call("server.stop", autostart=False)
            deadline = time.time() + 15
            while dc.is_alive(old) and time.time() < deadline:  # wait for the old one to really exit
                time.sleep(0.25)
            if dc.is_alive(old):
                print("error: the old daemon did not stop", file=sys.stderr)
                return 1
        info = dc.ensure_daemon()
        print(f"restarted (pid {info['pid']})")
        return 0
    if action == "url":
        info = dc.ensure_daemon()
        host = info.get("host") if info.get("host") not in (None, "", "127.0.0.1") else "127.0.0.1"
        print(f"http://{host}:{info['port']}/?token={info['token']}")
        print("Keep this link private: it gives full control of your agents.", file=sys.stderr)
        return 0
    if action == "logs":
        path = log_dir() / "daemon.log"
        print(path.read_text(encoding="utf-8")[-8000:] if path.exists() else "(no log yet)")
        return 0
    from drover.cli.cli_autostart import set_autostart

    print(set_autostart(args.value != "off"))
    return 0


def cmd_machine(args) -> int:
    if args.action == "ls":
        for m in dc.call("machine.list"):
            print(f"{m['alias']:<12} {m['target']:<28} {m['status']:<11} {m['error']}")
    elif args.action == "add":
        dc.call("machine.add", {"alias": args.alias, "target": args.target, "port": args.port,
                                "key": args.key, "install": args.install}, timeout=900)
        print(f"added {args.alias}")
    elif args.action == "rm":
        dc.call("machine.remove", {"alias": args.alias})
    else:
        result = dc.call("machine.test", {"target": args.alias or args.target, "port": args.port,
                                          "key": args.key}, timeout=120)
        print("\n".join(result["steps"]) or "-")
        if not result["ok"]:
            print(f"error: {result['error']}", file=sys.stderr)
            return 1
    return 0


def cmd_worktree(args) -> int:
    repo = args.repo or os.getcwd()
    if args.action == "ls":
        for w in dc.call("worktree.list", {"repo": repo}):
            print(f"{w.get('branch', '(detached)'):<28} {w['changes']:>3} changes  {w['path']}")
    elif args.action == "new":
        if args.run:
            pane = dc.call("pane.create", {"command": args.run, "cwd": repo, "name": args.name,
                                           "worktree": {"task": args.name, "base": args.base}})
            print(f"{pane['id']}  {pane['cwd']}")
        else:
            info = dc.call("worktree.create", {"repo": repo, "task": args.name, "base": args.base})
            print(f"{info['branch']}  {info['path']}")
    else:
        dc.call("worktree.remove", {"path": args.name, "force": args.force})
    return 0


def cmd_rules(args) -> int:
    if args.action == "ls":
        for r in dc.call("rules.list"):
            print(f"{r['id']:<10} {r['source']:<8} {r['rules']:>2} rules  {r['path']}")
        return 0
    result = dc.call("rules.test", {"pane": args.target, "kind": args.kind})
    print(f"{result['pane']} kind={result['kind']} title={result['title']!r}")
    for r in result["results"]:
        mark = "MATCH" if r["matched"] else "-"
        print(f"  {r['rule_id']:<22} {r['priority']:>5} {r['region']:<12} {r['state']:<8} {mark}")
    print(f"detected: {result['detected'] or '(none: activity fallback)'} · current state: {result['state']}")
    return 0
