//! Pure page-joining helpers for reading more than one screen from a full-screen agent (alternate screen).
//! Port of the pure half of `alt_screen_history_reader.py`; the scrolling loop lives with the pane session.

pub const WHEEL_UP: u32 = 64;
pub const WHEEL_DOWN: u32 = 65;
pub const NOTCHES_PER_PAGE: usize = 5;
pub const PAGE_SETTLE_SECS: f64 = 0.25;
pub const MAX_PAGES: usize = 40;

/// Join a page scrolled further up (`older`) onto what we have (`newer`) using their largest overlap.
pub fn merge_pages(older: &[String], newer: &[String]) -> Vec<String> {
    for size in (1..=older.len().min(newer.len())).rev() {
        let tail = &older[older.len() - size..];
        if tail == &newer[..size] && tail.iter().any(|l| !l.trim().is_empty()) {
            return older.iter().chain(&newer[size..]).cloned().collect();
        }
    }
    older.iter().chain(newer).cloned().collect()
}

/// Rows that did not move when the transcript scrolled: (header rows, footer rows).
pub fn fixed_chrome(first: &[String], scrolled: &[String]) -> (usize, usize) {
    let limit = first.len().min(scrolled.len()).saturating_sub(1);
    let mut top = 0;
    while top < limit && first[top] == scrolled[top] {
        top += 1;
    }
    let mut bottom = 0;
    while bottom < limit - top && first[first.len() - 1 - bottom] == scrolled[scrolled.len() - 1 - bottom] {
        bottom += 1;
    }
    (top, bottom)
}

/// SGR mouse wheel events at the middle of the pane.
pub fn wheel(button: u32, cols: usize, rows: usize, notches: usize) -> String {
    format!("\x1b[<{button};{};{}M", (cols / 2).max(1), (rows / 2).max(1)).repeat(notches)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn v(items: &[&str]) -> Vec<String> {
        items.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn merge_pages_uses_the_largest_overlap() {
        let newer = v(&["c", "d", "e"]);
        assert_eq!(merge_pages(&v(&["a", "b", "c", "d"]), &newer), v(&["a", "b", "c", "d", "e"]));
        assert_eq!(merge_pages(&v(&["x", "y"]), &newer), v(&["x", "y", "c", "d", "e"]));
    }

    #[test]
    fn merge_pages_ignores_blank_only_overlap() {
        assert_eq!(merge_pages(&v(&["a", ""]), &v(&["", "b"])), v(&["a", "", "", "b"]));
    }

    #[test]
    fn fixed_chrome_finds_header_and_footer() {
        let first = v(&["HEADER", "l5", "l6", "l7", "> input"]);
        let scrolled = v(&["HEADER", "l2", "l3", "l4", "> input"]);
        assert_eq!(fixed_chrome(&first, &scrolled), (1, 1));
        assert_eq!(fixed_chrome(&v(&["a", "b"]), &v(&["c", "d"])), (0, 0));
        assert_eq!(fixed_chrome(&[], &[]), (0, 0));
    }

    #[test]
    fn wheel_encodes_sgr_events() {
        assert_eq!(wheel(WHEEL_UP, 80, 24, 2), "\x1b[<64;40;12M\x1b[<64;40;12M");
    }
}
