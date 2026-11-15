"""Bundled detection rules evaluated against realistic Claude Code / shell screens."""

from __future__ import annotations

import pytest

from drover.app_paths import bundled_rules_dir
from drover.status.detection_rule_loader import load_rule_sets, match_agent_kind, parse_rule_file
from drover.status.status_detector import detect_kind_from_title, evaluate

PERMISSION_SCREEN = [
    "⏺ Bash(rm -rf build/)",
    "  ⎿  Running…",
    "",
    " Bash command",
    "",
    "   rm -rf build/",
    "   Delete build output",
    "",
    " Do you want to proceed?",
    " ❯ 1. Yes",
    "   2. Yes, and don't ask again for rm commands in /repo",
    "   3. No, and tell Claude what to do differently (esc)",
    "",
    "  Esc to cancel",
]

WORKING_SCREEN = [
    "⏺ Reading src/app.py",
    "",
    "✻ Pondering… (14s · ↑ 1.2k tokens · esc to interrupt)",
    "",
    "> ",
    "  ? for shortcuts",
]

THEME_PICKER_SCREEN = [
    "Welcome to Claude Code!",
    "",
    "Choose the text style that looks best with your terminal",
    "To change this later, run /theme",
    "",
    " ❯ 1. Dark mode ✔",
    "   2. Light mode",
    "   3. Dark mode (colorblind-friendly)",
    "",
    "  [code preview]",
]

PLAIN_PROMPT_SCREEN = ["$ ls", "README.md  src", "> ", "  ? for shortcuts"]


@pytest.fixture(scope="module")
def rule_sets():
    sets, errors = load_rule_sets(bundled_rules_dir(), None)
    assert errors == []
    return sets


def test_bundled_rule_sets_all_load(rule_sets):
    assert {"claude", "codex", "gemini", "opencode", "shell"} <= set(rule_sets)
    assert all(rs.source == "bundled" for rs in rule_sets.values())


def test_rules_are_sorted_by_priority_descending(rule_sets):
    priorities = [r.priority for r in rule_sets["claude"].rules]
    assert priorities == sorted(priorities, reverse=True)
    assert rule_sets["claude"].rules[0].id == "permission_prompt"


def test_permission_prompt_is_blocked(rule_sets):
    winner, results = evaluate(rule_sets["claude"], "", PERMISSION_SCREEN)
    assert winner == "blocked"
    assert "permission_prompt" in {r.rule_id for r in results if r.matched}


def test_do_you_want_to_proceed_alone_is_blocked(rule_sets):
    assert evaluate(rule_sets["claude"], "", ["Do you want to make this edit to app.py?"])[0] == "blocked"


def test_esc_to_interrupt_line_means_working(rule_sets):
    assert evaluate(rule_sets["claude"], "", WORKING_SCREEN)[0] == "working"


def test_permission_prompt_outranks_working_line(rule_sets):
    screen = WORKING_SCREEN + PERMISSION_SCREEN[8:]
    assert evaluate(rule_sets["claude"], "", screen)[0] == "blocked"


def test_first_run_theme_picker_is_blocked(rule_sets):
    winner, results = evaluate(rule_sets["claude"], "", THEME_PICKER_SCREEN)
    assert winner == "blocked"
    assert "selection_menu" in {r.rule_id for r in results if r.matched}


def test_plain_prompt_is_idle(rule_sets):
    assert evaluate(rule_sets["claude"], "", PLAIN_PROMPT_SCREEN)[0] == "idle"


def test_unrelated_output_matches_no_rule(rule_sets):
    winner, results = evaluate(rule_sets["claude"], "", ["PS C:\\> dir", "file.txt"])
    assert winner is None
    assert not any(r.matched for r in results)


def test_spinner_in_title_is_working(rule_sets):
    assert evaluate(rule_sets["claude"], "⠂ Claude Code", ["hi"])[0] == "working"


def test_idle_star_title_is_not_working(rule_sets):
    """Claude Code titles itself "✳ <topic>" while waiting at the prompt."""
    assert evaluate(rule_sets["claude"], "✳ Hỏi đáp chung", ["❯ xóa dòng đó đi"])[0] == "idle"


def test_evaluate_without_rule_set_returns_no_verdict():
    assert evaluate(None, "", ["x"]) == (None, [])


def test_detect_kind_from_title(rule_sets):
    assert detect_kind_from_title("✳ Claude Code", rule_sets) == "claude"
    assert detect_kind_from_title("PS C:\\repo", rule_sets) is None


@pytest.mark.parametrize("command, expected", [
    ("C:/x/claude.cmd --continue", "claude"),
    ("claude", "claude"),
    ("claude-code --resume", "claude"),
    ("codex resume --last", "codex"),
    ("bash -l", "shell"),
    ("cmd /c echo hi", "shell"),
    ("", "shell"),
    ("unknown-agent", "shell"),
])
def test_match_agent_kind_maps_launch_command(rule_sets, command, expected):
    assert match_agent_kind(command, rule_sets) == expected


def test_match_agent_kind_handles_quoted_path_with_spaces(rule_sets):
    # Expected to FAIL: split() keeps the leading quote and the stem becomes "Program".
    # Source: drover/status/detection_rule_loader.py:98 (match_agent_kind).
    assert match_agent_kind('"C:/Program Files/Claude/claude.exe" --continue', rule_sets) == "claude"


def test_user_rule_file_overrides_bundled_by_id(tmp_path):
    user = tmp_path / "rules"
    user.mkdir()
    (user / "claude.toml").write_text(
        'id = "claude"\n[[rules]]\nid = "custom"\nstate = "idle"\nregex = ["custom"]\n', encoding="utf-8")
    sets, errors = load_rule_sets(bundled_rules_dir(), user)
    assert errors == []
    assert sets["claude"].source == "user"
    assert len(sets["claude"].rules) == 1


def test_invalid_user_rule_files_are_reported_not_fatal(tmp_path):
    user = tmp_path / "rules"
    user.mkdir()
    (user / "broken.toml").write_text('id = "broken"\n[[rules]]\nstate = "angry"\nregex = ["x"]\n', encoding="utf-8")
    (user / "badre.toml").write_text('id = "badre"\n[[rules]]\nstate = "idle"\nregex = ["("]\n', encoding="utf-8")
    sets, errors = load_rule_sets(bundled_rules_dir(), user)
    assert "broken" not in sets and "badre" not in sets
    assert len(errors) == 2
    assert "claude" in sets


def test_parse_rule_file_rejects_unknown_region(tmp_path):
    path = tmp_path / "x.toml"
    path.write_text('id = "x"\n[[rules]]\nstate = "idle"\nregion = "sidebar"\nregex = ["x"]\n', encoding="utf-8")
    with pytest.raises(ValueError, match="bad region"):
        parse_rule_file(path, "user")
