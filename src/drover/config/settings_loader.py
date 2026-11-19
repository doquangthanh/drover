"""Load settings.toml / keys.toml / machines.toml with bundled defaults and hot reload."""

from __future__ import annotations

import copy
import logging
import tomllib
from pathlib import Path
from typing import Any

from drover.app_paths import config_dir

log = logging.getLogger(__name__)

DEFAULT_SETTINGS: dict[str, Any] = {
    "theme": "dark",
    "file_icons": "material",
    "prefix": "C-a",
    "tui_prefix": "C-b",  # `dr tui` only: Herdr/tmux-style prefix, so it does not clash with the web UI's
    "scrollback": 5000,
    "claude_subagent_hooks": True,  # claude panes report their sub-agents to the Flow board (per-pane --settings)
    "shell": "",  # empty = platform default
    "fs_roots": [],  # empty = home directory only
    "notify": {
        "blocked": ["toast", "desktop", "sound"],
        "done": ["toast", "desktop"],
        "exited": ["toast", "desktop"],
        "quiet_hours": "",  # e.g. "23:00-07:00"
    },
    "orchestration": {
        "max_panes": 0,  # 0 = no limit
        "max_depth": 3,
        "agents_may_answer_permission_prompts": "ask-user",  # never | ask-user | always
        "kill_children_on_parent_exit": True,  # `dr run --outlive-parent` keeps one helper running
        "notes": True,  # type "<dr from=...>" notes into a parent agent when its helper finishes, asks or exits
    },
    "agents": {
        "claude": {"command": "claude", "resume": "claude --continue"},
        "codex": {"command": "codex", "resume": "codex resume --last"},
        "gemini": {"command": "gemini", "resume": "gemini --resume"},
        "opencode": {"command": "opencode", "resume": "opencode --continue"},
    },
}

DEFAULT_SETTINGS_TOML = """# drover settings — reloads on save. See AGENTS.md in this folder.
# theme: dark | light | midnight | auto. Ctrl+A : "Theme" overrides it on one device.
theme = "dark"
# file_icons: material | badge | line | none  (icons in the Files tree; Settings can override per device)
file_icons = "material"
prefix = "C-a"
# prefix of the terminal UI (`dr` / `dr tui`), Herdr-style
tui_prefix = "C-b"
scrollback = 5000
# shell = "pwsh"
# fs_roots = ["C:/Users/me/PROJECT"]   # folders the in-app picker may browse

[notify]
blocked = ["toast", "desktop", "sound"]
done = ["toast", "desktop"]
exited = ["toast", "desktop"]
quiet_hours = ""

[orchestration]
max_panes = 0                     # live panes at once; 0 = no limit
max_depth = 3
agents_may_answer_permission_prompts = "ask-user"   # never | ask-user | always
kill_children_on_parent_exit = true   # helpers stop with the agent that started them (`dr run --outlive-parent` opts out)
notes = true                          # tell a parent agent when its helper finishes, needs an answer or exits
"""


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def read_toml(path: Path) -> dict:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except FileNotFoundError:
        return {}
    except (tomllib.TOMLDecodeError, OSError) as exc:
        log.warning("invalid config %s: %s", path, exc)
        return {}


class SettingsStore:
    """Holds merged settings; `reload_if_changed()` is polled by the daemon."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or config_dir()
        self.path = self.directory / "settings.toml"
        self._mtime = -1.0
        self.data: dict[str, Any] = copy.deepcopy(DEFAULT_SETTINGS)
        self.errors: list[str] = []
        self.ensure_files()
        self.reload_if_changed()

    def ensure_files(self) -> None:
        if not self.path.exists():
            self.path.write_text(DEFAULT_SETTINGS_TOML, encoding="utf-8")
        agents_md = self.directory / "AGENTS.md"
        if not agents_md.exists():
            from drover.config.config_agents_doc import CONFIG_AGENTS_MD

            agents_md.write_text(CONFIG_AGENTS_MD, encoding="utf-8")

    def reload_if_changed(self) -> bool:
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            return False
        if mtime == self._mtime:
            return False
        self._mtime = mtime
        self.errors = []
        try:
            with self.path.open("rb") as fh:
                user = tomllib.load(fh)
        except (tomllib.TOMLDecodeError, OSError) as exc:
            self.errors.append(f"settings.toml: {exc}")
            return True
        self.data = deep_merge(DEFAULT_SETTINGS, user)
        return True

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node
