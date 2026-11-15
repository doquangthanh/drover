"""Parse OSC 7501 ("Program Status Protocol") self-reports from raw terminal output.

Format: ESC ] 7501 ; key=value[:key=value...] (BEL | ESC \\)
Example: ESC]7501;state=blocked:app=my-agent BEL
"""

from __future__ import annotations

import re

_OSC_RE = re.compile(r"\x1b\]7501;([^\x07\x1b]*)(?:\x07|\x1b\\)")
_ALLOWED = {"working", "blocked", "idle", "done"}


def parse_osc7501(chunk: str) -> dict[str, str] | None:
    """Return the last report found in `chunk` as a dict, or None."""
    last: dict[str, str] | None = None
    for match in _OSC_RE.finditer(chunk):
        fields: dict[str, str] = {}
        for part in match.group(1).split(":"):
            key, _, value = part.partition("=")
            if key:
                fields[key.strip()] = value.strip()
        if fields.get("state") in _ALLOWED:
            last = fields
    return last
