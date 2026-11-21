"""Encode a mouse event as the xterm report an app in a pane asked for (DEC ?1000/?1002/?1003, SGR ?1006).

Pure functions (no Textual), so they are easy to test. Coordinates are 0-based cells inside the pane.
"""

from __future__ import annotations

WHEEL_UP = 64
WHEEL_DOWN = 65
_BUTTONS = {1: 0, 2: 1, 3: 2}  # Textual: 1 left, 2 middle, 3 right -> xterm button codes
_LEGACY_MAX = 223  # legacy (X10) encoding packs each value into one byte: 32 + value <= 255


def button_code(button: int, shift: bool = False, meta: bool = False, ctrl: bool = False) -> int | None:
    """xterm button code with modifier bits, or None for a button xterm cannot report."""
    code = _BUTTONS.get(button)
    if code is None:
        return None
    return code + (4 if shift else 0) + (8 if meta else 0) + (16 if ctrl else 0)


def mouse_report(code: int, x: int, y: int, pressed: bool, sgr: bool) -> str:
    """Bytes for one press/release (or wheel step). Legacy releases carry button 3; far cells are dropped."""
    if sgr:
        return f"\x1b[<{code};{x + 1};{y + 1}{'M' if pressed else 'm'}"
    if x > _LEGACY_MAX - 1 or y > _LEGACY_MAX - 1:
        return ""
    legacy = code if pressed else (code & ~3) | 3
    return "\x1b[M" + chr(32 + legacy) + chr(33 + x) + chr(33 + y)
