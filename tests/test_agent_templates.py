"""Role templates: ~/.config/drover/templates/<name>.md expanded by `dr run <template> "task"`."""

from __future__ import annotations

import json
import shlex
import sys

import pytest

from drover.cli import cli_commands_agents as agents
from drover.cli.agent_templates import list_templates, load_template, parse_template, templates_dir
from drover.cli.cli_main import build_parser

REVIEWER = """---
name: reviewer
description: Reviews a change, read-only
command: claude --model opus
---
You review code. Read only.
"""


def _write(name: str, text: str) -> None:
    folder = templates_dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.md").write_text(text, encoding="utf-8")


def test_template_argv_puts_instructions_then_task_in_one_argument():
    _write("reviewer", REVIEWER)
    t = load_template("reviewer")
    assert t is not None and t.description == "Reviews a change, read-only"
    assert t.argv("Review src/x.py") == ["claude", "--model", "opus", "You review code. Read only.\n\nReview src/x.py"]
    assert t.argv("") == ["claude", "--model", "opus", "You review code. Read only."]


def test_missing_or_unsafe_names_are_not_templates():
    assert load_template("claude") is None
    assert load_template("../etc/passwd") is None
    assert load_template("") is None


@pytest.mark.parametrize("text, message", [
    ("---\nname: x\n", "no closing ---"),
    ("---\nname: x\n---\nbody", "needs a `command:` line"),
    ("---\ncommand: claude 'oops\n---\n", "not valid shell words"),
])
def test_bad_templates_explain_the_problem(text, message, tmp_path):
    with pytest.raises(ValueError, match=message):
        parse_template(text, tmp_path / "x.md")


def test_list_reports_good_templates_and_errors_per_file():
    _write("reviewer", REVIEWER)
    _write("broken", "---\nname: broken\n---\n")
    found, errors = list_templates()
    assert [t.name for t in found] == ["reviewer"]
    assert len(errors) == 1 and "broken.md" in errors[0]


def test_dr_run_with_a_template_sends_the_expanded_command(monkeypatch):
    _write("reviewer", REVIEWER)
    sent = {}
    monkeypatch.setattr(agents, "call", lambda method, params=None, **kw: sent.update(params) or {"id": "%9"})
    args = build_parser().parse_args(["run", "--bg", "reviewer", "Review src/x.py"])
    assert agents.cmd_run(args) == 0
    assert sent["name"] == "reviewer"
    assert shlex.split(sent["command"]) == ["claude", "--model", "opus", "You review code. Read only.\n\nReview src/x.py"]


def test_dr_run_without_a_template_is_unchanged(monkeypatch):
    sent = {}
    monkeypatch.setattr(agents, "call", lambda method, params=None, **kw: sent.update(params) or {"id": "%9"})
    args = build_parser().parse_args(["run", "--bg", "--name", "t", "--", "codex", "write tests"])
    agents.cmd_run(args)
    # Windows quotes for cmd.exe (list2cmdline), elsewhere POSIX shlex quoting
    expected = 'codex "write tests"' if sys.platform == "win32" else "codex 'write tests'"
    assert sent["command"] == expected and sent["name"] == "t"


def test_dr_templates_json(capsys):
    _write("reviewer", REVIEWER)
    assert agents.cmd_templates(build_parser().parse_args(["templates", "--json"])) == 0
    out = json.loads(capsys.readouterr().out)
    assert [t["name"] for t in out["templates"]] == ["reviewer"]
