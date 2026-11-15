"""dr space / tab / pane: build layouts from scripts. Every command prints JSON with the ids it made."""

from __future__ import annotations

import json
import os

from drover.cli.cli_commands_agents import _join
from drover.daemon.daemon_client import call


def add_layout_parsers(sub) -> None:
    space = sub.add_parser("space", help="new | ls spaces (a folder with its tabs)")
    space.add_argument("action", choices=["new", "ls"])
    space.add_argument("--cwd", default="", help="folder for `new` (default: current)")
    space.add_argument("command", nargs="*", help="-- command for the first pane (empty = shell)")

    tab = sub.add_parser("tab", help="new | ls | rename | close tabs")
    tab.add_argument("action", choices=["new", "ls", "rename", "close"])
    tab.add_argument("target", nargs="?", default="", help="space id (new) or tab id")
    tab.add_argument("--name", default="")
    tab.add_argument("command", nargs="*", help="-- command for `new` (empty = shell)")

    pane = sub.add_parser("pane", help="split | move | swap | zoom | unzoom | share | focus panes")
    pane.add_argument("action", choices=["split", "move", "swap", "zoom", "unzoom", "share", "focus"])
    pane.add_argument("target", help="pane id or agent name ('self' inside a pane)")
    pane.add_argument("--direction", choices=["right", "down"], default="right")
    pane.add_argument("--name", default="")
    pane.add_argument("--new-tab", action="store_true", help="move: into a new tab of the same space")
    pane.add_argument("--share", type=float, default=0.5, help="share: fraction of the split (0.1-0.9)")
    # One list, read per action: split -> the command; swap -> the other pane; move -> the tab id.
    # (A separate optional positional would swallow the first word after `--`.)
    pane.add_argument("rest", nargs="*", help="split: -- command (empty = shell); swap: other pane; move: tab id")


def _print(result) -> int:
    print(json.dumps(result, indent=1))
    return 0


def _need(value: str, what: str) -> str:
    if not value:
        raise SystemExit(f"error: {what} is required")
    return value


def cmd_space(args) -> int:
    if args.action == "ls":
        return _print(call("state.get")["spaces"])
    return _print(call("space.create", {"cwd": os.path.abspath(args.cwd or os.getcwd()),
                                        "command": _join(args.command)}))


def cmd_tab(args) -> int:
    if args.action == "ls":
        return _print(call("state.get")["tabs"])
    if args.action == "new":
        return _print(call("tab.create", {"space": _need(args.target, "space id"), "name": args.name,
                                          "command": _join(args.command)}))
    tab_id = _need(args.target, "tab id")
    if args.action == "rename":
        call("tab.rename", {"tab": tab_id, "name": _need(args.name, "--name")})
    else:
        call("tab.close", {"tab": tab_id})
    return _print({"tab": tab_id})


def cmd_pane(args) -> int:
    pane, action = args.target, args.action
    other = args.rest[0] if args.rest else ""
    if action == "split":
        return _print(call("pane.split", {"pane": pane, "direction": args.direction, "name": args.name,
                                          "command": _join(args.rest)}))
    if action == "move":
        params = {"pane": pane, "direction": args.direction}
        if args.new_tab:
            params["new_tab"] = True
        else:
            params["tab"] = _need(other, "tab id (or --new-tab)")
        return _print(call("pane.move", params))
    if action == "swap":
        return _print(call("pane.swap", {"pane": pane, "target": _need(other, "the other pane")}))
    if action in ("zoom", "unzoom"):
        return _print(call("pane.zoom", {"pane": pane, "zoomed": action == "zoom"}))
    if action == "share":
        return _print(call("pane.share", {"pane": pane, "share": args.share}))
    call("pane.focus", {"pane": pane})
    return _print({"pane": pane})


COMMANDS = {"space": cmd_space, "tab": cmd_tab, "pane": cmd_pane}
