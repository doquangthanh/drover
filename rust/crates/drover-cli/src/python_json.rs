//! Text exactly as the Python CLI prints it: `json.dumps(v)`, `json.dumps(v, indent=1)` and `str(v)`.
//! Agents parse `dr ... --json` output, so the fast path must not change a byte (key order comes from the
//! daemon's reply: serde_json's `preserve_order`).

use serde_json::{Number, Value};

/// `json.dumps(v)`: separators `", "` / `": "`, ASCII only.
pub fn dumps(v: &Value) -> String {
    let mut out = String::new();
    write_value(&mut out, v, None, 0);
    out
}

/// `json.dumps(v, indent=1)`: one space per level, items end with `","`.
pub fn dumps_indent1(v: &Value) -> String {
    let mut out = String::new();
    write_value(&mut out, v, Some(1), 0);
    out
}

/// `str(v)` for the scalar values the CLI prints (strings unquoted, `None`, `True`, floats as Python repr).
/// Lists and dicts never reach a print in practice; they fall back to JSON text.
pub fn py_str(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        Value::Null => "None".into(),
        Value::Bool(b) => if *b { "True" } else { "False" }.into(),
        Value::Number(n) => number(n),
        other => dumps(other),
    }
}

fn write_value(out: &mut String, v: &Value, indent: Option<usize>, level: usize) {
    match v {
        Value::Null => out.push_str("null"),
        Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
        Value::Number(n) => out.push_str(&number(n)),
        Value::String(s) => write_string(out, s),
        Value::Array(items) if items.is_empty() => out.push_str("[]"),
        Value::Object(map) if map.is_empty() => out.push_str("{}"),
        Value::Array(items) => {
            out.push('[');
            for (i, item) in items.iter().enumerate() {
                separator(out, indent, level + 1, i == 0);
                write_value(out, item, indent, level + 1);
            }
            close(out, indent, level, ']');
        }
        Value::Object(map) => {
            out.push('{');
            for (i, (key, item)) in map.iter().enumerate() {
                separator(out, indent, level + 1, i == 0);
                write_string(out, key);
                out.push_str(": ");
                write_value(out, item, indent, level + 1);
            }
            close(out, indent, level, '}');
        }
    }
}

fn separator(out: &mut String, indent: Option<usize>, level: usize, first: bool) {
    match indent {
        None if !first => out.push_str(", "),
        None => {}
        Some(width) => {
            if !first {
                out.push(',');
            }
            out.push('\n');
            out.push_str(&" ".repeat(width * level));
        }
    }
}

fn close(out: &mut String, indent: Option<usize>, level: usize, bracket: char) {
    if let Some(width) = indent {
        out.push('\n');
        out.push_str(&" ".repeat(width * level));
    }
    out.push(bracket);
}

/// Python's `ensure_ascii` escaping: everything outside printable ASCII becomes `\uXXXX` (surrogate pairs above
/// the BMP), lowercase hex.
fn write_string(out: &mut String, s: &str) {
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\u{8}' => out.push_str("\\b"),
            '\u{c}' => out.push_str("\\f"),
            ' '..='~' => out.push(c),
            _ => {
                let mut units = [0u16; 2];
                for unit in c.encode_utf16(&mut units) {
                    out.push_str(&format!("\\u{unit:04x}"));
                }
            }
        }
    }
    out.push('"');
}

fn number(n: &Number) -> String {
    match n.as_f64() {
        Some(f) if n.is_f64() => float_repr(f),
        _ => n.to_string(),
    }
}

/// Python `repr(float)`: shortest round-trip digits; positional for 1e-4 <= |x| < 1e16 (always with a `.`),
/// otherwise `d.ddde+XX`.
fn float_repr(f: f64) -> String {
    if !f.is_finite() {
        return if f.is_nan() { "NaN" } else if f > 0.0 { "Infinity" } else { "-Infinity" }.into();
    }
    if f == 0.0 {
        return if f.is_sign_negative() { "-0.0" } else { "0.0" }.into();
    }
    let sci = format!("{:e}", f.abs()); // shortest digits, e.g. "1.5e3", "1e-5"
    let (mantissa, exp) = sci.split_once('e').unwrap_or((&sci, "0"));
    let exp: i32 = exp.parse().unwrap_or(0);
    let digits: String = mantissa.chars().filter(|c| *c != '.').collect();
    let sign = if f < 0.0 { "-" } else { "" };
    if (-4..16).contains(&exp) {
        let point = exp + 1; // digits before the decimal point
        let body = if point <= 0 {
            format!("0.{}{digits}", "0".repeat((-point) as usize))
        } else if point as usize >= digits.len() {
            format!("{digits}{}.0", "0".repeat(point as usize - digits.len()))
        } else {
            format!("{}.{}", &digits[..point as usize], &digits[point as usize..])
        };
        return format!("{sign}{body}");
    }
    let mantissa = if digits.len() > 1 { format!("{}.{}", &digits[..1], &digits[1..]) } else { digits };
    format!("{sign}{mantissa}e{}{:02}", if exp < 0 { '-' } else { '+' }, exp.abs())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn compact_matches_json_dumps() {
        let v: Value = serde_json::from_str(r#"{"b": 1, "a": [true, null, "x"], "e": {}, "l": []}"#).unwrap();
        assert_eq!(dumps(&v), r#"{"b": 1, "a": [true, null, "x"], "e": {}, "l": []}"#);
    }

    #[test]
    fn indent1_matches_json_dumps() {
        let v = json!([{"id": "%1", "n": [1, 2]}, []]);
        assert_eq!(dumps_indent1(&v), "[\n {\n  \"id\": \"%1\",\n  \"n\": [\n   1,\n   2\n  ]\n },\n []\n]");
    }

    #[test]
    fn strings_are_ascii_escaped_like_python() {
        assert_eq!(dumps(&json!("tiếng \"Việt\"\n\u{1}\u{7f}😀\\")),
                   r#""ti\u1ebfng \"Vi\u1ec7t\"\n\u0001\u007f\ud83d\ude00\\""#);
    }

    #[test]
    fn floats_use_python_repr() {
        for (f, s) in [(1.0, "1.0"), (100.0, "100.0"), (1763550000.123456, "1763550000.123456"), (0.0001, "0.0001"),
                       (1e-5, "1e-05"), (1.5e-7, "1.5e-07"), (1e16, "1e+16"), (1.2345e22, "1.2345e+22"), (-2.5, "-2.5"),
                       (123456789012345.6, "123456789012345.6"), (0.1, "0.1")] {
            assert_eq!(float_repr(f), s, "{f}");
        }
        assert_eq!(dumps(&json!(600)), "600");
        // parsed text must round-trip (serde_json's default float parser is off by an ulp here)
        let v: Value = serde_json::from_str("[1795095105.9013007, 1795095105.8232763]").unwrap();
        assert_eq!(dumps(&v), "[1795095105.9013007, 1795095105.8232763]");
    }

    #[test]
    fn py_str_scalars() {
        assert_eq!(py_str(&json!("idle")), "idle");
        assert_eq!(py_str(&Value::Null), "None");
        assert_eq!(py_str(&json!(false)), "False");
        assert_eq!(py_str(&json!(2.0)), "2.0");
    }
}
