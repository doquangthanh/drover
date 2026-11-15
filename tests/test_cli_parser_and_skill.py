"""dr CLI: parser shape and `dr skill` output. No daemon is contacted."""

from __future__ import annotations

import argparse

import pytest

from drover.cli import cli_commands_admin as admin
from drover.cli.cli_main import build_parser, main

CORE_COMMANDS = ["run", "ls", "send", "read", "wait", "attach", "kill", "status", "schema", "skill",
                 "server", "machine", "worktree", "rules", "prompt", "keys", "wait-output", "rename",
                 "space", "tab", "pane", "completion"]


def test_pane_split_keeps_every_word_after_the_separator_in_the_command():
    args = build_parser().parse_args(["pane", "split", "lead", "--direction", "down", "--", "codex", "--model", "x"])
    assert args.target == "lead" and args.direction == "down"
    assert args.rest == ["codex", "--model", "x"]


def test_pane_swap_and_prompt_flags_parse():
    p = build_parser()
    assert p.parse_args(["pane", "swap", "a", "b"]).rest == ["b"]
    args = p.parse_args(["prompt", "reviewer", "check the diff", "--wait", "--state", "done", "--timeout", "90"])
    assert (args.wait, args.state, args.timeout) == (True, ["done"], 90.0)
    assert p.parse_args(["keys", "reviewer", "esc", "ctrl+c"]).keys == ["esc", "ctrl+c"]
    assert p.parse_args(["space", "new", "--", "codex"]).command == ["codex"]


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish", "powershell"])
def test_completion_scripts_list_commands_flags_and_agent_names(shell, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["completion", shell])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for word in ("wait-output", "-l regex" if shell == "fish" else "--regex", "dr ls --names"):
        assert word in out
    if shell == "powershell":
        assert "Register-ArgumentCompleter" in out and "'server' = @('start'" in out
    if shell == "zsh":
        assert "bashcompinit" in out


def _subcommands(parser: argparse.ArgumentParser) -> dict:
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return action.choices


def test_parser_registers_every_core_subcommand():
    choices = _subcommands(build_parser())
    for name in CORE_COMMANDS:
        assert name in choices


def test_run_parses_flags_and_command_after_separator():
    args = build_parser().parse_args(["run", "--bg", "--name", "tests", "--", "codex", "write tests"])
    assert args.cmd == "run"
    assert args.bg is True
    assert args.name == "tests"
    assert "codex" in args.command and "write tests" in args.command


def test_wait_accepts_repeated_states_and_float_timeout():
    args = build_parser().parse_args(["wait", "tests", "--state", "done", "--state", "blocked",
                                      "--timeout", "900"])
    assert args.state == ["done", "blocked"]
    assert args.timeout == 900.0


def test_wait_rejects_unknown_state():
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["wait", "tests", "--state", "sleeping"])
    assert exc.value.code == 2


def test_no_subcommand_leaves_cmd_empty():
    assert build_parser().parse_args([]).cmd is None


def test_skill_text_is_printed_and_returns_zero(capsys):
    assert admin.cmd_skill(argparse.Namespace()) == 0
    out = capsys.readouterr().out
    assert "Working with other agents through drover" in out
    assert "dr wait tests --state done" in out
    assert "Exit code 2 = timeout" in out


def test_main_skill_exits_zero_with_instructions(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["skill"])
    assert exc.value.code == 0
    assert "dr kill" in capsys.readouterr().out
