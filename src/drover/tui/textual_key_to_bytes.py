"""Textual key events -> the bytes a terminal program expects on its stdin."""

from __future__ import annotations

from drover.core.terminal_key_names import encode_key

_CURSOR = {"up": "A", "down": "B", "right": "C", "left": "D", "home": "H", "end": "F"}
_MOD_CODE = {"shift": 2, "alt": 3, "ctrl": 5}  # xterm modifier parameter for arrows, home, end


def key_to_bytes(key: str, character: str | None, app_cursor: bool = False) -> str | None:
    """Bytes for one Textual key press, or None when the key has no terminal meaning (the caller ignores it)."""
    if character and len(character) == 1 and character.isprintable():
        return character  # letters, digits, symbols, space, non-ASCII: already the right text
    *mods, name = key.split("+")
    if name in _CURSOR and mods:
        codes = [_MOD_CODE[m] for m in mods if m in _MOD_CODE]
        return f"\x1b[1;{codes[0]}{_CURSOR[name]}" if len(codes) == 1 and len(codes) == len(mods) else None
    if name in _CURSOR and not mods:
        return ("\x1bO" if app_cursor else "\x1b[") + _CURSOR[name]
    try:
        return encode_key(key.replace("escape", "esc"))
    except ValueError:
        return None
