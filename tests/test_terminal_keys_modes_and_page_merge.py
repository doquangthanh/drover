"""Pure logic: key names, DEC mode tracking, alternate-screen page merging, layout swap/share."""

from __future__ import annotations

import pytest

from drover.core import split_layout_tree as layout
from drover.core.alt_screen_history_reader import fixed_chrome, merge_pages
from drover.core.terminal_key_names import encode_key, encode_keys
from drover.core.terminal_mode_tracker import TerminalModes


@pytest.mark.parametrize(("name", "data"), [
    ("esc", "\x1b"), ("Escape", "\x1b"), ("enter", "\r"), ("up", "\x1b[A"), ("shift+tab", "\x1b[Z"),
    ("ctrl+c", "\x03"), ("C-d", "\x04"), ("ctrl+[", "\x1b"), ("f5", "\x1b[15~"), ("alt+x", "\x1bx"),
])
def test_encode_key(name, data):
    assert encode_key(name) == data


def test_encode_keys_joins_and_rejects_unknown_or_empty():
    assert encode_keys(["down", "down", "enter"]) == "\x1b[B\x1b[B\r"
    with pytest.raises(ValueError, match="unknown key"):
        encode_keys(["ctrl+1"])
    with pytest.raises(ValueError):
        encode_keys([])


def test_modes_follow_set_and_reset_sequences():
    modes = TerminalModes()
    modes.feed("plain text, no escapes")
    assert not modes.scrollable_transcript
    modes.feed("\x1b[?1049h\x1b[?1002;1006h\x1b[?2004h")
    assert modes.alt_screen and modes.mouse and modes.mouse_sgr and modes.bracketed_paste
    assert modes.scrollable_transcript
    modes.feed("\x1b[?1006l")
    assert not modes.scrollable_transcript
    modes.feed("\x1b[?1049l\x1b[?2004l")
    assert not modes.alt_screen and not modes.bracketed_paste


def test_merge_pages_uses_the_largest_overlap():
    newer = ["c", "d", "e"]
    assert merge_pages(["a", "b", "c", "d"], newer) == ["a", "b", "c", "d", "e"]
    assert merge_pages(["x", "y"], newer) == ["x", "y", "c", "d", "e"]  # no overlap: keep both


def test_merge_pages_ignores_blank_only_overlap():
    assert merge_pages(["a", ""], ["", "b"]) == ["a", "", "", "b"]


def test_fixed_chrome_finds_header_and_footer():
    first = ["HEADER", "l5", "l6", "l7", "> input"]
    scrolled = ["HEADER", "l2", "l3", "l4", "> input"]
    assert fixed_chrome(first, scrolled) == (1, 1)
    assert fixed_chrome(["a", "b"], ["c", "d"]) == (0, 0)


def test_swap_leaves_and_set_share():
    tree = layout.insert(layout.insert(layout.leaf("%1"), "%1", "%2"), "%2", "%3", "col")
    swapped = layout.swap_leaves(tree, "%1", "%3")
    assert layout.pane_ids(swapped) == ["%3", "%2", "%1"]
    assert layout.path_to(tree, "%3") == "bb"
    shared = layout.set_share(tree, "%3", 0.8)
    assert abs(shared["b"]["ratio"] - 0.2) < 1e-9 and shared["ratio"] == 0.5
    with pytest.raises(ValueError, match="alone"):
        layout.set_share(layout.leaf("%1"), "%1", 0.5)
