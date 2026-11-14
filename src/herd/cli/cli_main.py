"""`hd` command line: the same API agents use from inside their panes."""

from __future__ import annotations

import argparse
import sys

from herd.cli import cli_commands_admin as admin
from herd.cli import cli_commands_agents as agents
from herd.daemon.daemon_client import DaemonUnavailable, RpcFailure


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="hd", description="herd: run and watch coding agents")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("app", help="open the herd window (default)")

    run = sub.add_parser("run", help="start an agent or command in a pane")
    run.add_argument("--bg", action="store_true", help="don't attach; print the pane id")
    run.add_argument("--name", default="")
    run.add_argument("--cwd", default="")
    run.add_argument("--on", default="", help="machine alias from machines.toml")
    run.add_argument("--worktree", default="", metavar="TASK", help="new git worktree for this task")
    run.add_argument("--split", action="store_true", help="split the caller's tab instead of a new tab")
    run.add_argument("command", nargs=argparse.REMAINDER, help="-- command and args (empty = shell)")

    ls = sub.add_parser("ls", help="list agents and their state")
    ls.add_argument("--json", action="store_true")

    send = sub.add_parser("send", help="type text into an agent")
    send.add_argument("target")
    send.add_argument("text")
    send.add_argument("--no-enter", action="store_true")

    read = sub.add_parser("read", help="print an agent's screen and scrollback")
    read.add_argument("target")
    read.add_argument("--lines", type=int, default=0)
    read.add_argument("--json", action="store_true")

    wait = sub.add_parser("wait", help="block until an agent reaches a state")
    wait.add_argument("target")
    wait.add_argument("--state", action="append", choices=["done", "idle", "blocked", "working", "exited"])
    wait.add_argument("--timeout", type=float, default=600)

    attach = sub.add_parser("attach", help="full-screen one agent in this terminal (Ctrl+\\ detaches)")
    attach.add_argument("target")

    kill = sub.add_parser("kill", help="stop an agent")
    kill.add_argument("target")
    kill.add_argument("--tree", action="store_true", help="also stop the helpers it started")

    sub.add_parser("status", help="server, machines and agent counts")
    sub.add_parser("schema", help="print the JSON-RPC API")
    sub.add_parser("skill", help="print instructions that teach an agent to use hd")
    admin.add_admin_parsers(sub)
    return p


COMMANDS = {
    "run": agents.cmd_run, "ls": agents.cmd_ls, "send": agents.cmd_send, "read": agents.cmd_read,
    "wait": agents.cmd_wait, "attach": agents.cmd_attach, "kill": agents.cmd_kill,
    "status": admin.cmd_status, "schema": admin.cmd_schema, "skill": admin.cmd_skill,
    "server": admin.cmd_server, "machine": admin.cmd_machine, "worktree": admin.cmd_worktree,
    "rules": admin.cmd_rules,
}


def _utf8_output() -> None:
    """Agent screens contain box-drawing characters and emoji; a Windows console or pipe defaults to cp1252 and `hd read` crashed."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # not a text stream (captured by a test, closed)
            pass


def main(argv: list[str] | None = None) -> None:
    _utf8_output()
    args = build_parser().parse_args(argv)
    if args.cmd in (None, "app"):
        from herd.desktop.desktop_window_launcher import main as open_app

        open_app()
        return
    try:
        code = COMMANDS[args.cmd](args) or 0
    except RpcFailure as exc:
        print(f"error: {exc}", file=sys.stderr)
        code = exc.code if exc.code > 0 else 1
    except DaemonUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        code = 10
    except KeyboardInterrupt:
        code = 130
    sys.exit(code)


if __name__ == "__main__":
    main()
