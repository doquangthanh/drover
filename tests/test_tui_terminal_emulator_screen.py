from drover.tui.terminal_emulator_screen import TerminalEmulatorScreen


def text(screen: TerminalEmulatorScreen, y: int) -> str:
    return "".join(t for t, _ in screen.row_runs(y)).rstrip()


def test_colours_are_kept_per_run():
    s = TerminalEmulatorScreen(20, 3)
    s.feed("\x1b[31mhi\x1b[0m ok")
    runs = s.row_runs(0)
    assert runs[0][0] == "hi" and runs[0][1].fg == "red"
    assert text(s, 0) == "hi ok"


def test_truecolor_and_256_colour():
    s = TerminalEmulatorScreen(20, 3)
    s.feed("\x1b[38;2;1;2;3mA\x1b[48;5;200mB")
    runs = s.row_runs(0)
    assert runs[0][1].fg == "010203"
    assert runs[1][1].bg == "ff00d7"


def test_alt_screen_restores_main_text():
    s = TerminalEmulatorScreen(20, 3)
    s.feed("main text")
    s.feed("\x1b[?1049h\x1b[2J\x1b[Halt app")
    assert text(s, 0) == "alt app"
    assert s.modes.alt_screen
    s.feed("\x1b[?1049l")
    assert text(s, 0) == "main text"
    assert not s.modes.alt_screen


def test_alt_screen_sequence_split_across_one_chunk():
    s = TerminalEmulatorScreen(20, 3)
    s.feed("before\x1b[?1049hinside\x1b[?1049lafter")
    assert text(s, 0) == "beforeafter"  # `inside` went to the alt screen only


def test_app_cursor_and_bracketed_paste_flags():
    s = TerminalEmulatorScreen(20, 3)
    s.feed("\x1b[?1h\x1b[?2004h")
    assert s.app_cursor and s.modes.bracketed_paste
    s.feed("\x1b[?1l\x1b[?2004l")
    assert not s.app_cursor and not s.modes.bracketed_paste


def test_resize_and_version_bump():
    s = TerminalEmulatorScreen(20, 3)
    v = s.version
    s.resize(30, 5)
    assert (s.cols, s.rows) == (30, 5) and s.version > v
    s.feed("x")
    assert text(s, 0) == "x"


def test_wide_char_second_cell_is_empty():
    s = TerminalEmulatorScreen(10, 2)
    s.feed("漢a")
    assert text(s, 0) == "漢a"
