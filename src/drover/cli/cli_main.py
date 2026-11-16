"""`dr` command line: the same API agents use from inside their panes."""

from __future__ import annotations

import argparse
import sys

from drover.cli import cli_commands_admin as admin
from drover.cli import cli_commands_agent_input as agent_input
from drover.cli import cli_commands_agents as agents
from drover.cli import cli_commands_layout as layout_cmds
from drover.cli import cli_hook_claude as hook_claude
from drover.cli import cli_shell_completion as completion
from drover.daemon.daemon_client import DaemonUnavailable, RpcFailure


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="dr", description="drover: run and watch coding agents")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("app", help="open the drover window")

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
    ls.add_argument("--names", action="store_true", help="only agent names (used by shell completion)")

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

    sub.add_parser("tui", help="terminal UI in this terminal (default when Textual is installed)")
    sub.add_parser("status", help="server, machines and agent counts")
    sub.add_parser("schema", help="print the JSON-RPC API")
    sub.add_parser("skill", help="print instructions that teach an agent to use dr")
    admin.add_admin_parsers(sub)
    agent_input.add_agent_input_parsers(sub)
    layout_cmds.add_layout_parsers(sub)
    completion.add_completion_parser(sub)
    hook_claude.add_hook_parser(sub)
    return p


def _textual_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("textual") is not None


def _cmd_tui(_args) -> int:
    try:
        from drover.tui.tui_app import main as run_tui
    except ModuleNotFoundError as exc:
        if exc.name != "textual":
            raise
        print("error: the terminal UI needs Textual. Install it with: pip install 'drover[tui]'", file=sys.stderr)
        return 1
    return run_tui()


COMMANDS = {
    "run": agents.cmd_run, "ls": agents.cmd_ls, "send": agents.cmd_send, "read": agents.cmd_read,
    "wait": agents.cmd_wait, "attach": agents.cmd_attach, "kill": agents.cmd_kill,
    "status": admin.cmd_status, "schema": admin.cmd_schema, "skill": admin.cmd_skill,
    "server": admin.cmd_server, "machine": admin.cmd_machine, "worktree": admin.cmd_worktree,
    "rules": admin.cmd_rules, **agent_input.COMMANDS, **layout_cmds.COMMANDS,
    "completion": lambda args: completion.cmd_completion(args, build_parser()),
    "hook": hook_claude.cmd_hook, "tui": _cmd_tui,
}


def _utf8_output() -> None:
    """Agent screens contain box-drawing characters and emoji; a Windows console or pipe defaults to cp1252 and `dr read` crashed.
    stdin too: `dr prompt <agent> -` read a piped Vietnamese prompt as cp1252 mojibake (sent to the agent and the tree log)."""
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):  # not a text stream (captured by a test, closed)
            pass


def main(argv: list[str] | None = None) -> None:
    _utf8_output()
    args = build_parser().parse_args(argv)
    if args.cmd is None and _textual_available():  # plain `dr` opens the terminal UI; `dr app` the desktop window
        sys.exit(_cmd_tui(args))
    if args.cmd in (None, "app"):
        from drover.desktop.desktop_window_launcher import main as open_app

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
