//! Whether the person has typed into a pane since their last Enter. Guards parent notes: the daemon never types
//! a note into a half-written message. Port of `DraftTracker` in `parent_notes.py`.

/// A draft older than this is treated as abandoned, as in Herdr.
pub const DRAFT_HOLD: f64 = 60.0;

#[derive(Default, Clone, Debug)]
pub struct DraftTracker {
    pub pending: bool,
    pub key_at: f64,
}

/// Drop escape sequences (arrows, focus reports, mouse): they are not typing.
fn strip_escapes(data: &str) -> String {
    let mut out = String::new();
    let mut chars = data.chars().peekable();
    while let Some(c) = chars.next() {
        if c != '\x1b' {
            out.push(c);
            continue;
        }
        match chars.next() {
            Some('[') => {
                for n in chars.by_ref() {
                    if ('@'..='~').contains(&n) {
                        break;
                    }
                }
            }
            Some(']') => {
                while let Some(n) = chars.next() {
                    if n == '\x07' || (n == '\x1b' && chars.next_if_eq(&'\\').is_some()) {
                        break;
                    }
                }
            }
            Some('O') => {
                chars.next();
            }
            _ => {}
        }
    }
    out
}

impl DraftTracker {
    pub fn feed(&mut self, data: &str, now: f64) {
        let text = strip_escapes(data);
        if text.is_empty() {
            return;
        }
        self.key_at = now;
        // After Enter, Ctrl+C or Ctrl+U the line starts empty.
        let parts: Vec<&str> = text.split(['\r', '\n', '\x03', '\x15']).collect();
        if parts.len() > 1 {
            self.pending = false;
        }
        if parts.last().is_some_and(|tail| tail.chars().any(|c| c >= ' ' && c != '\x7f')) {
            self.pending = true;
        }
    }

    pub fn blocks(&self, now: f64) -> bool {
        self.pending && now - self.key_at < DRAFT_HOLD
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn typing_holds_until_enter_and_ignores_escapes() {
        let mut d = DraftTracker::default();
        d.feed("\x1b[A\x1b[I", 1.0);
        assert!(!d.blocks(1.0));
        d.feed("half typ", 2.0);
        assert!(d.blocks(3.0));
        assert!(!d.blocks(2.0 + DRAFT_HOLD + 1.0));
        d.feed("ed\r", 4.0);
        assert!(!d.blocks(4.0));
        d.feed("x\x15", 5.0);
        assert!(!d.blocks(5.0));
    }
}
