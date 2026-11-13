"""PaneScreen (pyte): visible text, scrollback, last-N reads, search, resilience."""

from __future__ import annotations

from herd.core.pane_screen_text import PaneScreen


def test_read_text_returns_visible_output():
    screen = PaneScreen(40, 5, 100)
    screen.feed("first line\r\nsecond line\r\n")
    text = screen.read_text()
    assert "first line" in text and "second line" in text


def test_scrolled_off_lines_stay_in_scrollback():
    screen = PaneScreen(40, 3, 100)
    for i in range(10):
        screen.feed(f"row {i}\r\n")
    text = screen.read_text()
    assert "row 0" in text and "row 9" in text


def test_read_last_n_lines_returns_tail():
    screen = PaneScreen(40, 3, 100)
    for i in range(6):
        screen.feed(f"row {i}\r\n")
    assert screen.read_text(2).splitlines()[-1] == "row 5"
    assert len(screen.read_text(2).splitlines()) == 2


def test_search_is_case_insensitive_and_numbers_lines():
    screen = PaneScreen(40, 5, 100)
    screen.feed("alpha\r\nERROR: boom\r\nomega\r\n")
    hits = screen.search("error")
    assert hits == [(2, "ERROR: boom")]


def test_garbage_escape_sequences_do_not_raise():
    screen = PaneScreen(40, 5, 100)
    screen.feed("\x1b[99999;;;Zxyz\x1b]0;title\x07ok")
    assert "ok" in screen.read_text()


def test_resize_keeps_existing_text():
    screen = PaneScreen(40, 5, 100)
    screen.feed("hi there\r\n")
    screen.resize(60, 10)
    assert "hi there" in screen.read_text()
