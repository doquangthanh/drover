//! Rebuilds a pane's terminal as ANSI text from the emulator's grid: scrollback, screen, colours, links, cursor and
//! input modes. A viewer that (re)attaches gets this instead of the raw output once the raw replay buffer has dropped
//! its oldest chunks, so it sees the whole history (up to the `scrollback` setting) and the keys it sends still match
//! what the program expects (mouse, bracketed paste, application cursor keys).
//! Not restored: the scroll region, tab stops and, while a full-screen app runs, the main screen behind it.

use std::fmt::Write;

use alacritty_terminal::grid::{Dimensions, Row};
use alacritty_terminal::index::{Column, Line};
use alacritty_terminal::term::TermMode;
use alacritty_terminal::term::cell::{Cell, Flags};
use alacritty_terminal::vte::ansi::{Color, NamedColor};

use crate::screen::PaneScreen;

const STYLE: Flags = Flags::BOLD
    .union(Flags::DIM)
    .union(Flags::ITALIC)
    .union(Flags::ALL_UNDERLINES)
    .union(Flags::INVERSE)
    .union(Flags::HIDDEN)
    .union(Flags::STRIKEOUT);

#[derive(Clone, Copy, PartialEq)]
struct Pen {
    fg: Color,
    bg: Color,
    flags: Flags,
}

impl Pen {
    fn of(cell: &Cell) -> Self {
        Pen { fg: cell.fg, bg: cell.bg, flags: cell.flags & STYLE }
    }

    fn sgr(&self, out: &mut String) {
        out.push_str("\x1b[0");
        for (flag, code) in [(Flags::BOLD, ";1"), (Flags::DIM, ";2"), (Flags::ITALIC, ";3"), (Flags::INVERSE, ";7"),
                             (Flags::HIDDEN, ";8"), (Flags::STRIKEOUT, ";9")] {
            if self.flags.contains(flag) {
                out.push_str(code);
            }
        }
        if self.flags.intersects(Flags::ALL_UNDERLINES) {
            out.push_str(";4");
        }
        color(out, self.fg, 30, 90, 38);
        color(out, self.bg, 40, 100, 48);
        out.push('m');
    }
}

/// `base` for colours 0-7, `bright` for 8-15, `ext` for 256-colour and truecolour; defaults emit nothing.
fn color(out: &mut String, c: Color, base: u16, bright: u16, ext: u16) {
    let _ = match c {
        Color::Indexed(i) => write!(out, ";{ext};5;{i}"),
        Color::Spec(rgb) => write!(out, ";{ext};2;{};{};{}", rgb.r, rgb.g, rgb.b),
        Color::Named(n) => {
            let i = n as u16;
            let dim = NamedColor::DimBlack as u16;
            match i {
                0..=7 => write!(out, ";{}", base + i),
                8..=15 => write!(out, ";{}", bright + i - 8),
                _ if (dim..dim + 8).contains(&i) => write!(out, ";{}", base + i - dim),
                _ => Ok(()), // foreground, background, cursor colours: the terminal's default
            }
        }
    };
}

fn blank(cell: &Cell) -> bool {
    cell.c == ' ' && cell.bg == Color::Named(NamedColor::Background) && !cell.flags.intersects(STYLE)
        && cell.hyperlink().is_none()
}

struct Writer {
    out: String,
    pen: Pen,
    link: Option<String>,
}

impl Writer {
    fn set_link(&mut self, uri: Option<String>) {
        if uri != self.link {
            let _ = write!(self.out, "\x1b]8;;{}\x1b\\", uri.as_deref().unwrap_or(""));
            self.link = uri;
        }
    }

    /// One grid row; true when it soft-wraps into the next one (the text then continues without a line break).
    fn row(&mut self, row: &Row<Cell>, cols: usize) -> bool {
        let wraps = row[Column(cols - 1)].flags.contains(Flags::WRAPLINE);
        let end = if wraps { cols } else { (0..cols).rev().find(|&x| !blank(&row[Column(x)])).map_or(0, |x| x + 1) };
        for x in 0..end {
            let cell = &row[Column(x)];
            if cell.flags.intersects(Flags::WIDE_CHAR_SPACER | Flags::LEADING_WIDE_CHAR_SPACER) {
                continue; // the wide char before it covers this column; a leading spacer is redone by wrapping
            }
            let pen = Pen::of(cell);
            if pen != self.pen {
                pen.sgr(&mut self.out);
                self.pen = pen;
            }
            self.set_link(cell.hyperlink().map(|h| h.uri().to_string()));
            self.out.push(cell.c);
            if let Some(extra) = cell.zerowidth() {
                self.out.extend(extra);
            }
        }
        wraps
    }
}

impl PaneScreen {
    /// The whole terminal as text that recreates it in a freshly reset viewer of the same size.
    pub fn snapshot(&self) -> String {
        let term = self.term();
        let grid = term.grid();
        let (cols, rows, history) = (grid.columns(), grid.screen_lines() as i32, grid.history_size() as i32);
        let mode = *term.mode();
        let default_pen = Pen { fg: Color::Named(NamedColor::Foreground), bg: Color::Named(NamedColor::Background),
                                flags: Flags::empty() };
        let mut w = Writer { out: String::with_capacity((history + rows) as usize * 64), pen: default_pen, link: None };
        w.out.push_str("\x1b[0m");
        if mode.contains(TermMode::ALT_SCREEN) {
            w.out.push_str("\x1b[?1049h\x1b[H\x1b[2J");
        }
        // Every screen row is written, blank ones too, so the last `rows` lines land exactly on the screen.
        for y in -history..rows {
            let wraps = w.row(&grid[Line(y)], cols);
            if !wraps && y < rows - 1 {
                w.set_link(None);
                if w.pen != default_pen {
                    w.out.push_str("\x1b[0m"); // a line scrolled in takes the current background (xterm, BCE)
                    w.pen = default_pen;
                }
                w.out.push_str("\r\n");
            }
        }
        w.set_link(None);
        let cursor = &grid.cursor;
        let _ = write!(w.out, "\x1b[{};{}H", cursor.point.line.0 + 1, cursor.point.column.0 + 1);
        Pen::of(&cursor.template).sgr(&mut w.out); // the attributes the program is currently writing with
        modes(&mut w.out, mode);
        w.out
    }
}

fn modes(out: &mut String, mode: TermMode) {
    for (flag, n) in [(TermMode::APP_CURSOR, 1), (TermMode::MOUSE_REPORT_CLICK, 1000), (TermMode::MOUSE_DRAG, 1002),
                      (TermMode::MOUSE_MOTION, 1003), (TermMode::FOCUS_IN_OUT, 1004), (TermMode::UTF8_MOUSE, 1005),
                      (TermMode::SGR_MOUSE, 1006), (TermMode::BRACKETED_PASTE, 2004)] {
        if mode.contains(flag) {
            let _ = write!(out, "\x1b[?{n}h");
        }
    }
    if !mode.contains(TermMode::LINE_WRAP) {
        out.push_str("\x1b[?7l");
    }
    if !mode.contains(TermMode::SHOW_CURSOR) {
        out.push_str("\x1b[?25l");
    }
    if mode.contains(TermMode::APP_KEYPAD) {
        out.push_str("\x1b=");
    }
    if mode.contains(TermMode::INSERT) {
        out.push_str("\x1b[4h");
    }
    if mode.contains(TermMode::LINE_FEED_NEW_LINE) {
        out.push_str("\x1b[20h");
    }
}

#[cfg(test)]
#[path = "screen_snapshot_tests.rs"]
mod tests;
