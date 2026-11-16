import pytest

from drover.tui.textual_key_to_bytes import key_to_bytes


@pytest.mark.parametrize("key,char,app,expected", [
    ("a", "a", False, "a"),
    ("A", "A", False, "A"),
    ("space", " ", False, " "),
    ("é", "é", False, "é"),
    ("up", None, False, "\x1b[A"),
    ("up", None, True, "\x1bOA"),
    ("ctrl+c", "\x03", False, "\x03"),
    ("shift+tab", None, False, "\x1b[Z"),
    ("escape", "\x1b", False, "\x1b"),
    ("enter", "\r", False, "\r"),
    ("backspace", "\x7f", False, "\x7f"),
    ("ctrl+left", None, False, "\x1b[1;5D"),
    ("shift+up", None, False, "\x1b[1;2A"),
    ("alt+x", None, False, "\x1bx"),
    ("f5", None, False, "\x1b[15~"),
    ("pageup", None, False, "\x1b[5~"),
])
def test_key_bytes(key, char, app, expected):
    assert key_to_bytes(key, char, app) == expected


def test_unknown_key_is_ignored():
    assert key_to_bytes("ctrl+shift+f13", None) is None
