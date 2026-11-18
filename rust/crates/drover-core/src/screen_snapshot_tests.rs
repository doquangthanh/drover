//! Round trip: feed output to a screen, write its snapshot into a fresh screen of the same size, and the two must
//! match cell by cell (text, colours, styles, wrapping, links), with the same cursor and input modes.

use super::*;

const KEPT: Flags = STYLE.union(Flags::WRAPLINE).union(Flags::WIDE_CHAR).union(Flags::WIDE_CHAR_SPACER);

fn rebuilt(src: &PaneScreen, cols: usize, rows: usize) -> PaneScreen {
    let mut dst = PaneScreen::new(cols, rows, 1000);
    dst.feed(src.snapshot().as_bytes());
    dst
}

fn cells(s: &PaneScreen) -> Vec<String> {
    let grid = s.term().grid();
    let (cols, rows, history) = (grid.columns(), grid.screen_lines() as i32, grid.history_size() as i32);
    (-history..rows)
        .map(|y| {
            (0..cols)
                .map(|x| {
                    let c = &grid[Line(y)][Column(x)];
                    format!("{}{:?}{:?}{:?}{:?}{:?}", c.c, c.zerowidth(), c.fg, c.bg, c.flags & KEPT,
                            c.hyperlink().map(|h| h.uri().to_string()))
                })
                .collect()
        })
        .collect()
}

fn assert_same(a: &PaneScreen, b: &PaneScreen) {
    assert_eq!(a.all_lines(), b.all_lines());
    let (ca, cb) = (cells(a), cells(b));
    assert_eq!(ca.len(), cb.len(), "line count");
    for (i, (x, y)) in ca.iter().zip(&cb).enumerate() {
        assert_eq!(x, y, "line {i}");
    }
    assert_eq!(a.term().grid().cursor.point, b.term().grid().cursor.point, "cursor");
    let modes = TermMode::ANY.difference(TermMode::VI);
    assert_eq!(*a.term().mode() & modes, *b.term().mode() & modes, "modes");
}

#[test]
fn history_screen_and_colours_survive() {
    let mut s = PaneScreen::new(40, 6, 1000);
    for i in 0..60 {
        s.feed(format!("\x1b[3{}mline {i}\x1b[0m plain \x1b[1;4;48;5;{i}mbold\x1b[0m \x1b[38;2;1;2;{i}mrgb\x1b[0m\r\n",
                       i % 8).as_bytes());
    }
    s.feed(b"\x1b[7;3;9mstyled\x1b[0m \x1b[93;101mbright\x1b[0m");
    assert_same(&s, &rebuilt(&s, 40, 6));
}

#[test]
fn soft_wrapped_lines_and_wide_chars() {
    let mut s = PaneScreen::new(20, 5, 1000);
    s.feed("tiếng việt có dấu, một dòng rất dài để bị gãy\r\n".as_bytes());
    s.feed("1234567890123456789漢字漢字 e\u{301}\r\n".as_bytes()); // wide char at the last column wraps; combining mark
    s.feed("😀😀😀😀😀😀😀😀😀😀😀😀\r\n".as_bytes());
    assert_same(&s, &rebuilt(&s, 20, 5));
}

#[test]
fn cursor_blank_rows_and_pen() {
    let mut s = PaneScreen::new(30, 8, 1000);
    s.feed(b"top\r\n\r\n\x1b[44m  coloured blanks  \x1b[0m\r\n");
    s.feed(b"\x1b[2;5H\x1b[32m"); // cursor up in the middle, writing green
    let r = rebuilt(&s, 30, 8);
    assert_same(&s, &r);
    assert_eq!(r.term().grid().cursor.template.fg, s.term().grid().cursor.template.fg);
}

#[test]
fn input_modes_come_back() {
    let mut s = PaneScreen::new(30, 5, 1000);
    s.feed(b"\x1b[?1h\x1b=\x1b[?1000h\x1b[?1002h\x1b[?1006h\x1b[?1004h\x1b[?2004h\x1b[?25l> ");
    let r = rebuilt(&s, 30, 5);
    assert_same(&s, &r);
    assert_eq!(r.modes(), s.modes());
}

#[test]
fn full_screen_app() {
    let mut s = PaneScreen::new(30, 5, 1000);
    s.feed(b"shell output\r\n$ vim\r\n\x1b[?1049h\x1b[H\x1b[2J~\r\n~\r\n\x1b[7m status \x1b[0m\x1b[1;1H");
    let r = rebuilt(&s, 30, 5);
    assert!(r.modes().alt_screen);
    assert_eq!(r.visible_lines(), s.visible_lines());
    assert_eq!(r.term().grid().cursor.point, s.term().grid().cursor.point);
}

#[test]
fn hyperlinks_survive() {
    let mut s = PaneScreen::new(40, 4, 1000);
    s.feed(b"see \x1b]8;;https://example.com/a\x1b\\the docs\x1b]8;;\x1b\\ now\r\n");
    assert_same(&s, &rebuilt(&s, 40, 4));
}
