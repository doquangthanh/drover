//! A pressed key (as a GUI toolkit reports it) -> the bytes a terminal program expects (xterm conventions).
//! Plain text is not handled here: it arrives through the input method (IME), so composed text such as
//! Vietnamese Telex reaches the agent as finished words.

#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct Mods {
    pub ctrl: bool,
    pub alt: bool,
    pub shift: bool,
}

impl Mods {
    /// xterm modifier parameter: 1 + shift(1) + alt(2) + ctrl(4); None when no modifier is held.
    fn param(self) -> Option<u8> {
        let n = 1 + self.shift as u8 + 2 * self.alt as u8 + 4 * self.ctrl as u8;
        (n > 1).then_some(n)
    }
}

fn cursor_key(final_byte: char, mods: Mods, app_cursor: bool) -> String {
    match mods.param() {
        Some(p) => format!("\x1b[1;{p}{final_byte}"),
        None if app_cursor => format!("\x1bO{final_byte}"),
        None => format!("\x1b[{final_byte}"),
    }
}

fn tilde_key(code: u8, mods: Mods) -> String {
    match mods.param() {
        Some(p) => format!("\x1b[{code};{p}~"),
        None => format!("\x1b[{code}~"),
    }
}

fn function_key(n: u8, mods: Mods) -> Option<String> {
    match n {
        1..=4 => {
            let c = (b'P' + n - 1) as char;
            Some(match mods.param() {
                Some(p) => format!("\x1b[1;{p}{c}"),
                None => format!("\x1bO{c}"),
            })
        }
        5..=12 => Some(tilde_key([15, 17, 18, 19, 20, 21, 23, 24][(n - 5) as usize], mods)),
        _ => None,
    }
}

/// Bytes for `key` (lower-case name: "enter", "up", "f5", "a", "[") with `mods`. None = not a terminal key here;
/// leave it to the input method (plain or shifted text).
pub fn keystroke_bytes(key: &str, mods: Mods, app_cursor: bool) -> Option<String> {
    let alt = |s: &str| if mods.alt { format!("\x1b{s}") } else { s.to_string() };
    let named = match key {
        "enter" => Some(alt("\r")),
        "escape" => Some("\x1b".to_string()),
        "tab" if mods.shift => Some("\x1b[Z".to_string()),
        "tab" => Some(alt("\t")),
        "backspace" if mods.ctrl => Some(alt("\x08")),
        "backspace" => Some(alt("\x7f")),
        "space" if mods.ctrl => Some("\0".to_string()),
        "up" => Some(cursor_key('A', mods, app_cursor)),
        "down" => Some(cursor_key('B', mods, app_cursor)),
        "right" => Some(cursor_key('C', mods, app_cursor)),
        "left" => Some(cursor_key('D', mods, app_cursor)),
        "home" => Some(cursor_key('H', mods, app_cursor)),
        "end" => Some(cursor_key('F', mods, app_cursor)),
        "insert" => Some(tilde_key(2, mods)),
        "delete" => Some(tilde_key(3, mods)),
        "pageup" => Some(tilde_key(5, mods)),
        "pagedown" => Some(tilde_key(6, mods)),
        _ => None,
    };
    if named.is_some() {
        return named;
    }
    if let Some(n) = key.strip_prefix('f').and_then(|n| n.parse::<u8>().ok()) {
        return function_key(n, mods);
    }
    let mut chars = key.chars();
    let (Some(c), None) = (chars.next(), chars.next()) else { return None };
    if mods.ctrl {
        let byte = match c {
            'a'..='z' => Some(c as u8 - b'a' + 1),
            '@' | '2' => Some(0),
            '[' | '3' => Some(0x1b),
            '\\' | '4' => Some(0x1c),
            ']' | '5' => Some(0x1d),
            '^' | '6' => Some(0x1e),
            '_' | '-' | '7' => Some(0x1f),
            '/' => Some(0x1f),
            '8' | '?' => Some(0x7f),
            _ => None,
        }?;
        return Some(alt(&(byte as char).to_string()));
    }
    if mods.alt {
        let c = if mods.shift { c.to_ascii_uppercase() } else { c };
        return Some(format!("\x1b{c}"));
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    const NONE: Mods = Mods { ctrl: false, alt: false, shift: false };
    const CTRL: Mods = Mods { ctrl: true, alt: false, shift: false };
    const ALT: Mods = Mods { ctrl: false, alt: true, shift: false };

    #[test]
    fn named_keys_and_cursor_modes() {
        assert_eq!(keystroke_bytes("enter", NONE, false).as_deref(), Some("\r"));
        assert_eq!(keystroke_bytes("backspace", NONE, false).as_deref(), Some("\x7f"));
        assert_eq!(keystroke_bytes("up", NONE, false).as_deref(), Some("\x1b[A"));
        assert_eq!(keystroke_bytes("up", NONE, true).as_deref(), Some("\x1bOA"));
        assert_eq!(keystroke_bytes("left", CTRL, true).as_deref(), Some("\x1b[1;5D"));
        assert_eq!(keystroke_bytes("tab", Mods { shift: true, ..NONE }, false).as_deref(), Some("\x1b[Z"));
        assert_eq!(keystroke_bytes("delete", NONE, false).as_deref(), Some("\x1b[3~"));
        assert_eq!(keystroke_bytes("f1", NONE, false).as_deref(), Some("\x1bOP"));
        assert_eq!(keystroke_bytes("f5", CTRL, false).as_deref(), Some("\x1b[15;5~"));
    }

    #[test]
    fn control_and_alt_chords() {
        assert_eq!(keystroke_bytes("c", CTRL, false).as_deref(), Some("\x03"));
        assert_eq!(keystroke_bytes("[", CTRL, false).as_deref(), Some("\x1b"));
        assert_eq!(keystroke_bytes("space", CTRL, false).as_deref(), Some("\0"));
        assert_eq!(keystroke_bytes("b", ALT, false).as_deref(), Some("\x1bb"));
        assert_eq!(keystroke_bytes("b", Mods { alt: true, shift: true, ..NONE }, false).as_deref(), Some("\x1bB"));
    }

    #[test]
    fn plain_text_is_left_to_the_input_method() {
        assert_eq!(keystroke_bytes("a", NONE, false), None);
        assert_eq!(keystroke_bytes("a", Mods { shift: true, ..NONE }, false), None);
        assert_eq!(keystroke_bytes("space", NONE, false), None);
    }
}
