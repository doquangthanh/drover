"""Named keys ("esc", "up", "ctrl+c", "shift+tab") -> the bytes a terminal sends for them."""

from __future__ import annotations

KEYS = {
    "esc": "\x1b", "escape": "\x1b", "enter": "\r", "return": "\r", "tab": "\t", "shift+tab": "\x1b[Z",
    "backspace": "\x7f", "space": " ", "delete": "\x1b[3~", "del": "\x1b[3~", "insert": "\x1b[2~",
    "up": "\x1b[A", "down": "\x1b[B", "right": "\x1b[C", "left": "\x1b[D",
    "home": "\x1b[H", "end": "\x1b[F", "pageup": "\x1b[5~", "pgup": "\x1b[5~",
    "pagedown": "\x1b[6~", "pgdn": "\x1b[6~",
    **{f"f{n}": seq for n, seq in zip(range(1, 13), (
        "\x1bOP", "\x1bOQ", "\x1bOR", "\x1bOS", "\x1b[15~", "\x1b[17~", "\x1b[18~", "\x1b[19~",
        "\x1b[20~", "\x1b[21~", "\x1b[23~", "\x1b[24~"), strict=True)},
}


def encode_key(name: str) -> str:
    """Bytes for one key name. Raises ValueError for names it does not know."""
    key = name.strip().lower()
    if key in KEYS:
        return KEYS[key]
    if key.startswith(("ctrl+", "c-")):
        letter = key.split("+", 1)[-1] if "+" in key else key[2:]
        if len(letter) == 1 and "a" <= letter <= "z":
            return chr(ord(letter) - 96)
        if letter in ("[", "\\", "]", "^", "_"):
            return chr(ord(letter) - 64)
    if key.startswith("alt+") and len(key) == 5:
        return "\x1b" + name.strip()[-1]
    raise ValueError(f"unknown key '{name}' (try esc, enter, tab, up, down, ctrl+c, shift+tab, f1)")


def encode_keys(names: list[str]) -> str:
    if not names:
        raise ValueError("no keys given")
    return "".join(encode_key(n) for n in names)
