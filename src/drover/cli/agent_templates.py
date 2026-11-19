"""Role templates for `dr run <template> "task"` (Herdr-style): ~/.config/drover/templates/<name>.md.

A template is Markdown with a small frontmatter:

    ---
    name: reviewer
    description: Reviews a change, read-only
    command: claude --model opus
    ---
    You review code. Read only; do not edit files or start agents. ...

`dr run reviewer "Review src/x.py"` starts `command` with one extra argument: the body, a blank line, then the task.
"""

from __future__ import annotations

import re
import shlex
from dataclasses import dataclass
from pathlib import Path

from drover.app_paths import config_dir

_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


@dataclass
class AgentTemplate:
    name: str
    description: str
    command: str
    body: str
    path: Path

    def argv(self, task: str) -> list[str]:
        """The command with the instructions and the task as its first prompt."""
        prompt = "\n\n".join(part for part in (self.body.strip(), task.strip()) if part)
        return shlex.split(self.command) + ([prompt] if prompt else [])


def templates_dir() -> Path:
    return config_dir() / "templates"


def parse_template(text: str, path: Path) -> AgentTemplate:
    """Frontmatter is `key: value` lines between two `---` lines; no YAML needed."""
    meta: dict[str, str] = {}
    body = text
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        end = next((i for i, line in enumerate(lines[1:], 1) if line.strip() == "---"), None)
        if end is None:
            raise ValueError(f"{path.name}: frontmatter has no closing ---")
        for line in lines[1:end]:
            if ":" in line and not line.lstrip().startswith("#"):
                key, value = line.split(":", 1)
                meta[key.strip().lower()] = value.strip().strip("\"'")
        body = "\n".join(lines[end + 1:])
    command = meta.get("command", "").strip()
    if not command:
        raise ValueError(f"{path.name}: frontmatter needs a `command:` line (e.g. command: claude)")
    try:
        shlex.split(command)
    except ValueError as exc:
        raise ValueError(f"{path.name}: command is not valid shell words: {exc}") from None
    return AgentTemplate(meta.get("name") or path.stem, meta.get("description", ""), command, body, path)


def load_template(name: str) -> AgentTemplate | None:
    """The template called `name`, or None when there is no such file (so `dr run claude` stays a program)."""
    if not _NAME_RE.match(name or ""):
        return None
    path = templates_dir() / f"{name}.md"
    if not path.is_file():
        return None
    return parse_template(path.read_text(encoding="utf-8"), path)


def list_templates() -> tuple[list[AgentTemplate], list[str]]:
    """All templates by name, plus one error line per file that could not be read."""
    found, errors = [], []
    folder = templates_dir()
    for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        try:
            found.append(parse_template(path.read_text(encoding="utf-8"), path))
        except (OSError, UnicodeDecodeError, ValueError) as exc:
            errors.append(str(exc))
    return found, errors
