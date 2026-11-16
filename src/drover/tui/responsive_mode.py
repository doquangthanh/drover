"""Layout mode for a terminal size (cells)."""

from __future__ import annotations

WIDE_MIN_WIDTH = 100
NARROW_MAX_WIDTH = 60
NARROW_MAX_HEIGHT = 15


def mode_for(width: int, height: int) -> str:
    """"wide": sidebar docked + split tree; "medium": sidebar as overlay + split tree; "narrow": one pane at a time."""
    if width < NARROW_MAX_WIDTH or height < NARROW_MAX_HEIGHT:
        return "narrow"
    return "wide" if width >= WIDE_MIN_WIDTH else "medium"
