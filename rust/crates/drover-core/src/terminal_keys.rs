//! Named keys ("esc", "up", "ctrl+c", "shift+tab") -> the bytes a terminal sends. Port of `terminal_key_names.py`.

const F_KEYS: [&str; 12] = [
    "\x1bOP", "\x1bOQ", "\x1bOR", "\x1bOS", "\x1b[15~", "\x1b[17~", "\x1b[18~", "\x1b[19~", "\x1b[20~", "\x1b[21~",
    "\x1b[23~", "\x1b[24~",
];

fn named(key: &str) -> Option<&'static str> {
    Some(match key {
        "esc" | "escape" => "\x1b",
        "enter" | "return" => "\r",
        "tab" => "\t",
        "shift+tab" => "\x1b[Z",
        "backspace" => "\x7f",
        "space" => " ",
        "delete" | "del" => "\x1b[3~",
        "insert" => "\x1b[2~",
        "up" => "\x1b[A",
        "down" => "\x1b[B",
        "right" => "\x1b[C",
        "left" => "\x1b[D",
        "home" => "\x1b[H",
        "end" => "\x1b[F",
        "pageup" | "pgup" => "\x1b[5~",
        "pagedown" | "pgdn" => "\x1b[6~",
        _ => {
            let n: usize = key.strip_prefix('f')?.parse().ok()?;
            return F_KEYS.get(n.checked_sub(1)?).copied();
        }
    })
}

/// Bytes for one key name; Err with a hint for names it does not know.
pub fn encode_key(name: &str) -> Result<String, String> {
    let key = name.trim().to_lowercase();
    if let Some(seq) = named(&key) {
        return Ok(seq.to_string());
    }
    let ctrl = key.strip_prefix("ctrl+").or_else(|| key.strip_prefix("c-"));
    if let Some(letter) = ctrl {
        let mut chars = letter.chars();
        if let (Some(c), None) = (chars.next(), chars.next()) {
            if c.is_ascii_lowercase() {
                return Ok(((c as u8 - 96) as char).to_string());
            }
            if "[\\]^_".contains(c) {
                return Ok(((c as u8 - 64) as char).to_string());
            }
        }
    }
    if key.starts_with("alt+") && key.chars().count() == 5 {
        return Ok(format!("\x1b{}", name.trim().chars().last().unwrap_or(' ')));
    }
    Err(format!("unknown key '{name}' (try esc, enter, tab, up, down, ctrl+c, shift+tab, f1)"))
}

pub fn encode_keys(names: &[String]) -> Result<String, String> {
    if names.is_empty() {
        return Err("no keys given".into());
    }
    names.iter().map(|n| encode_key(n)).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn encode_key_table() {
        for (name, data) in [
            ("esc", "\x1b"),
            ("Escape", "\x1b"),
            ("enter", "\r"),
            ("up", "\x1b[A"),
            ("shift+tab", "\x1b[Z"),
            ("ctrl+c", "\x03"),
            ("C-d", "\x04"),
            ("ctrl+[", "\x1b"),
            ("f5", "\x1b[15~"),
            ("alt+x", "\x1bx"),
        ] {
            assert_eq!(encode_key(name).as_deref(), Ok(data), "{name}");
        }
    }

    #[test]
    fn encode_keys_joins_and_rejects_unknown_or_empty() {
        let keys = |v: &[&str]| v.iter().map(|s| s.to_string()).collect::<Vec<_>>();
        assert_eq!(encode_keys(&keys(&["down", "down", "enter"])).as_deref(), Ok("\x1b[B\x1b[B\r"));
        assert!(encode_keys(&keys(&["ctrl+1"])).unwrap_err().contains("unknown key"));
        assert!(encode_keys(&[]).is_err());
        assert!(encode_key("f13").is_err() && encode_key("f0").is_err());
    }
}
