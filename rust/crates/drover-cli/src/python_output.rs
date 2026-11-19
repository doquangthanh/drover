//! Python stdio and string behaviour the CLI output depends on: `print()` (with `\r\n` on Windows), stdin read
//! with universal newlines, `str.ljust` and truthiness.

use std::io::{Read, Write};
use std::sync::OnceLock;

use serde_json::Value;

static CONSUMED_STDIN: OnceLock<Vec<u8>> = OnceLock::new();

/// `sys.stdin.read().rstrip("\n")`, UTF-8 with replacement; Windows stdin turns `\r\n` and `\r` into `\n`.
/// The raw bytes are kept so a command handed to Python afterwards gets the same input.
pub fn read_stdin() -> String {
    let mut raw = Vec::new();
    let _ = std::io::stdin().read_to_end(&mut raw);
    let mut text = String::from_utf8_lossy(&raw).into_owned();
    let _ = CONSUMED_STDIN.set(raw);
    if cfg!(windows) {
        text = text.replace("\r\n", "\n").replace('\r', "\n");
    }
    text.trim_end_matches('\n').to_string()
}

/// Bytes `read_stdin` already took, if it ran.
pub fn consumed_stdin() -> Option<&'static [u8]> {
    CONSUMED_STDIN.get().map(Vec::as_slice)
}

/// `print(text)`: Python text streams on Windows write each `\n` as `\r\n`.
/// False when the stream is gone (closed pipe).
fn python_print(mut stream: impl Write, text: &str) -> bool {
    let mut line = format!("{text}\n");
    if cfg!(windows) {
        line = line.replace('\n', "\r\n");
    }
    stream.write_all(line.as_bytes()).and_then(|()| stream.flush()).is_ok()
}

pub fn print_out(text: &str) -> bool {
    python_print(std::io::stdout().lock(), text)
}

/// `print(text, file=sys.stderr)`; returns `code` for `return Outcome::Exit(print_err(..))`.
pub fn print_err(text: &str, code: i32) -> i32 {
    python_print(std::io::stderr().lock(), text);
    code
}

/// `str.ljust(width)`: pad with spaces to `width` code points.
pub fn ljust(s: &str, width: usize) -> String {
    format!("{s}{}", " ".repeat(width.saturating_sub(s.chars().count())))
}

/// Python `bool(v)` for a JSON value.
pub fn truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64() != Some(0.0),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn ljust_counts_code_points() {
        assert_eq!(ljust("ab", 4), "ab  ");
        assert_eq!(ljust("tiếng", 6), "tiếng ");
        assert_eq!(ljust("long", 2), "long");
    }

    #[test]
    fn truthiness() {
        assert!(!truthy(&json!("")) && !truthy(&Value::Null) && !truthy(&json!(0)));
        assert!(truthy(&json!("%3")) && truthy(&json!(1)));
    }
}
