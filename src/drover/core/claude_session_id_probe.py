"""Which Claude Code conversation a pane runs, so a restart resumes that exact one (`claude --resume <id>`).

`claude --continue` reopens the newest conversation in the folder, so two Claude panes in one repo would both come
back as the same conversation. Claude Code keeps `<config>/sessions/<pid>.json` (pid, sessionId, cwd) for each
running process, and the transcript in `<config>/projects/<folder>/<sessionId>.jsonl`. These files are Claude's own,
not a documented API: anything missing or odd gives None, and the caller keeps the rule's `claude --continue`.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Iterable
from pathlib import Path

# A UUID only: the id goes into a command line, so nothing else may get through.
SESSION_ID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def claude_config_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def running_session_id(pids: Iterable[int], config_dir: Path | None = None) -> str | None:
    """Conversation id of the first pid that is a running Claude Code process; None if none is."""
    base = config_dir or claude_config_dir()
    for pid in pids:
        try:
            data = json.loads((base / "sessions" / f"{pid}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        sid = data.get("sessionId") if isinstance(data, dict) else None
        if isinstance(sid, str) and SESSION_ID.fullmatch(sid):
            return sid
    return None


def has_transcript(sid: str, config_dir: Path | None = None) -> bool:
    """`claude --resume` fails on a conversation with no message yet; its transcript appears with the first one."""
    base = config_dir or claude_config_dir()
    return any((base / "projects").glob(f"*/{sid}.jsonl"))


def resume_command(sid: str) -> str:
    return f"claude --resume {sid}"
