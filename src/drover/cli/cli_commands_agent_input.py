"""dr prompt / keys / wait-output / rename: drive an agent's UI without raw keystrokes."""

from __future__ import annotations

import sys

from drover.daemon.daemon_client import call

STATES = ["done", "idle", "blocked", "working", "exited"]


def add_agent_input_parsers(sub) -> None:
    prompt = sub.add_parser("prompt", help="submit a prompt; refuses an agent on a permission prompt")
    prompt.add_argument("target")
    prompt.add_argument("text", help="the prompt ('-' reads it from stdin)")
    prompt.add_argument("--wait", action="store_true", help="wait until the agent settles")
    prompt.add_argument("--state", action="append", choices=STATES, help="with --wait: states that count")
    prompt.add_argument("--timeout", type=float, default=600)

    keys = sub.add_parser("keys", help="press keys in an agent: esc, enter, up, down, tab, ctrl+c, shift+tab")
    keys.add_argument("target")
    keys.add_argument("keys", nargs="+", metavar="KEY")

    wait_output = sub.add_parser("wait-output", help="block until text or a regex shows in a pane's output")
    wait_output.add_argument("target")
    wait_output.add_argument("pattern")
    wait_output.add_argument("--regex", action="store_true", help="treat the pattern as a regular expression")
    wait_output.add_argument("--lines", type=int, default=80, help="search the last N lines (default 80)")
    wait_output.add_argument("--timeout", type=float, default=600)
    wait_output.add_argument("--json", action="store_true")

    rename = sub.add_parser("rename", help="give an agent a name other agents can use")
    rename.add_argument("target")
    rename.add_argument("name")


def cmd_prompt(args) -> int:
    text = sys.stdin.read().rstrip("\n") if args.text == "-" else args.text
    params = {"pane": args.target, "text": text, "wait": args.wait, "timeout": args.timeout}
    if args.state:
        params["states"] = args.state
    result = call("pane.prompt", params, timeout=args.timeout + 10)
    print(result["state"])
    return 0


def cmd_keys(args) -> int:
    result = call("pane.keys", {"pane": args.target, "keys": args.keys})
    print(f"pressed {' '.join(result['keys'])} in {result['pane']}")
    return 0


def cmd_wait_output(args) -> int:
    import json

    params = {"pane": args.target, "pattern": args.pattern, "regex": args.regex, "lines": args.lines,
              "timeout": args.timeout}
    result = call("pane.wait_output", params, timeout=args.timeout + 10)
    print(json.dumps(result) if args.json else result["matched_line"])
    return 0


def cmd_rename(args) -> int:
    result = call("pane.rename", {"pane": args.target, "name": args.name})
    print(f"{result['pane']} is now '{result['name']}'")
    return 0


COMMANDS = {"prompt": cmd_prompt, "keys": cmd_keys, "wait-output": cmd_wait_output, "rename": cmd_rename}
