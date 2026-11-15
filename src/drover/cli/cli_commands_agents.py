"""dr run / ls / send / read / wait / attach / kill."""

from __future__ import annotations

import json
import os
import shlex
import sys
import time

from drover.daemon.daemon_client import DaemonUnavailable, RpcFailure, call

STATE_LABEL = {"blocked": "needs you", "working": "working", "done": "done", "idle": "idle",
               "exited": "exited", "stopped": "stopped"}


def _join(command: list[str]) -> str:
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        return ""
    if sys.platform == "win32":
        import subprocess

        return subprocess.list2cmdline(command)
    return shlex.join(command)


def cmd_run(args) -> int:
    params = {"command": _join(args.command), "name": args.name, "cwd": args.cwd or os.getcwd()}
    if args.on:
        params["machine"] = args.on
        params["cwd"] = args.cwd  # remote default = remote home
    if args.worktree:
        params["worktree"] = {"task": args.worktree}
    caller = os.environ.get("DR_PANE_ID")
    if args.split and caller:
        state = call("state.get")
        pane = next((p for p in state["panes"] if p["id"] == caller), None)
        if pane:
            params.update(tab_id=pane["tab_id"], split_from=caller)
    pane = call("pane.create", params)
    if args.bg:
        print(pane["id"])
        return 0
    from drover.cli.cli_attach_terminal import attach

    return attach(pane["id"])


def _age(since: float) -> str:
    seconds = max(0, int(time.time() - since))
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{seconds // size}{unit}"
    return f"{seconds}s"


def _print_names() -> int:
    """For shell completion: local agent names, silently nothing when the daemon is not running."""
    try:
        panes = call("state.get", timeout=2, autostart=False)["panes"]
    except (DaemonUnavailable, RpcFailure):
        return 0
    print("\n".join(sorted({p["name"] for p in panes})))
    return 0


def cmd_ls(args) -> int:
    if getattr(args, "names", False):
        return _print_names()
    state = call("state.get")
    panes = list(state["panes"])
    for machine in state.get("machines", []):
        panes += machine.get("snapshot", {}).get("panes", [])
    if args.json:
        print(json.dumps(panes, indent=1))
        return 0
    spaces = {s["id"]: s["name"] for s in state["spaces"]}
    for machine in state.get("machines", []):
        spaces.update({s["id"]: s["name"] for s in machine.get("snapshot", {}).get("spaces", [])})
    rows = [("ID", "NAME", "AGENT", "STATE", "SPACE", "MACHINE", "AGE")]
    for p in panes:
        rows.append((p["id"], p["name"], p["kind"], STATE_LABEL.get(p["state"], p["state"]),
                     spaces.get(p["space_id"], ""), p.get("machine", "local"), _age(p["created_at"])))
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(rows[0]))]
    for row in rows:
        print("  ".join(str(c).ljust(w) for c, w in zip(row, widths, strict=True)).rstrip())
    return 0


def cmd_send(args) -> int:
    result = call("pane.send", {"pane": args.target, "text": args.text, "enter": not args.no_enter})
    print(f"sent to {result['pane']}")
    return 0


def cmd_read(args) -> int:
    result = call("pane.read", {"pane": args.target, "lines": args.lines or None})
    print(json.dumps(result) if args.json else result["text"])
    return 0


def cmd_wait(args) -> int:
    states = args.state or ["done", "idle", "blocked"]
    result = call("pane.wait", {"pane": args.target, "states": states, "timeout": args.timeout},
                  timeout=args.timeout + 10)
    print(result["state"])
    return 0


def cmd_kill(args) -> int:
    call("pane.close", {"pane": args.target, "subtree": args.tree})
    return 0


def cmd_attach(args) -> int:
    from drover.cli.cli_attach_terminal import attach

    state = call("state.get")
    known = {p["id"]: p for p in state["panes"]}
    target = args.target if args.target in known or ":" in args.target else None
    if target is None:
        matches = [p["id"] for p in state["panes"] if p["name"] == args.target]
        if not matches:
            print(f"error: no agent named '{args.target}'", file=sys.stderr)
            return 3
        target = matches[0]
    return attach(target)
