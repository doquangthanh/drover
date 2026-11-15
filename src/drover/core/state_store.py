"""Persist layout + pane metadata so a restarted daemon can offer to resume agents."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class StateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("ignoring unreadable session file: %s", exc)
            return {}

    def save(self, data: dict[str, Any]) -> None:
        """Atomic write: temp file in the same folder, then replace."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix="session-", suffix=".json", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=1)
            os.replace(tmp, self.path)
        except OSError as exc:
            log.warning("could not save session: %s", exc)
            try:
                os.unlink(tmp)
            except OSError:
                pass
