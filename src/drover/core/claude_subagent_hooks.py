"""Per-pane Claude Code hooks: drover adds `--settings <file>` when it starts `claude`, so sub-agents (Task/Agent tool)
show as lanes on the Flow board. The user's ~/.claude/settings.json is never touched; Claude merges these hooks with
the user's own. The hooks run `dr hook claude` (prints nothing, so nothing reaches Claude's context or tokens).
"""

from __future__ import annotations

import json
from pathlib import Path

from drover.app_paths import state_dir
from drover.self_command import fast_cli_command


def hook_command() -> str:
    """Shell command line for the hook. Forward slashes + double quotes work in Git Bash, cmd and sh alike."""
    return " ".join('"' + part.replace("\\", "/") + '"' for part in fast_cli_command()) + " hook claude"


def settings_file() -> Path:
    """Write (only when it changed) and return the settings file holding drover's sub-agent hooks."""
    hook = [{"hooks": [{"type": "command", "command": hook_command(), "timeout": 10}]}]
    body = json.dumps({"hooks": {"SubagentStart": hook, "SubagentStop": hook}}, indent=2)
    path = state_dir() / "claude-subagent-hooks.json"
    if not path.exists() or path.read_text(encoding="utf-8") != body:
        path.write_text(body, encoding="utf-8")
    return path


def with_subagent_hooks(argv: list[str]) -> list[str]:
    """argv of a `claude` pane with `--settings <file>` right after the program; anything else unchanged."""
    if not argv or Path(argv[0]).stem.lower() != "claude" or "--settings" in argv:
        return argv
    try:
        return [argv[0], "--settings", str(settings_file()), *argv[1:]]
    except OSError:  # state dir not writable: run claude without the Flow lanes rather than not at all
        return argv
