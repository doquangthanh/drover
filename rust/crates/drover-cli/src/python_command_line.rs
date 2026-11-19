//! `cli_commands_agents._join`: argv -> one command string, exactly like Python. Windows uses
//! `subprocess.list2cmdline` (MS C runtime quoting), elsewhere `shlex.join`. A leading `--` is dropped.

pub fn join(command: &[String]) -> String {
    let words = match command.split_first() {
        Some((first, rest)) if first == "--" => rest,
        _ => command,
    };
    if cfg!(windows) { list2cmdline(words) } else { shlex_join(words) }
}

/// CPython `subprocess.list2cmdline`.
pub fn list2cmdline(args: &[String]) -> String {
    let mut out = String::new();
    for arg in args {
        if !out.is_empty() {
            out.push(' ');
        }
        let quote = arg.is_empty() || arg.contains(' ') || arg.contains('\t');
        if quote {
            out.push('"');
        }
        let mut backslashes = 0usize;
        for c in arg.chars() {
            match c {
                '\\' => backslashes += 1,
                '"' => {
                    out.push_str(&"\\".repeat(backslashes * 2));
                    backslashes = 0;
                    out.push_str("\\\"");
                }
                _ => {
                    out.push_str(&"\\".repeat(backslashes));
                    backslashes = 0;
                    out.push(c);
                }
            }
        }
        out.push_str(&"\\".repeat(backslashes));
        if quote {
            out.push_str(&"\\".repeat(backslashes)); // doubled before the closing quote
            out.push('"');
        }
    }
    out
}

/// CPython `shlex.join` (`shlex.quote` per word).
pub fn shlex_join(args: &[String]) -> String {
    args.iter().map(|a| shlex_quote(a)).collect::<Vec<_>>().join(" ")
}

fn shlex_quote(s: &str) -> String {
    if s.is_empty() {
        return "''".into();
    }
    let safe = |c: char| c.is_ascii_alphanumeric() || "_@%+=:,./-".contains(c);
    if s.chars().all(safe) {
        return s.into();
    }
    format!("'{}'", s.replace('\'', "'\"'\"'"))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn v(words: &[&str]) -> Vec<String> {
        words.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn list2cmdline_matches_cpython() {
        // expected values printed by CPython 3.12 subprocess.list2cmdline
        assert_eq!(list2cmdline(&v(&["claude", "-p", "hi there"])), r#"claude -p "hi there""#);
        assert_eq!(list2cmdline(&v(&["a\"b", "", "c\\d", "e f\\", "g\\\"h"])), r#"a\"b "" c\d "e f\\" g\\\"h"#);
        assert_eq!(list2cmdline(&v(&["tab\there", "trail\\\\"])), "\"tab\there\" trail\\\\");
    }

    #[test]
    fn shlex_join_matches_cpython() {
        assert_eq!(shlex_join(&v(&["codex", "write tests", "", "it's", "a=b,c/d"])), r#"codex 'write tests' '' 'it'"'"'s' a=b,c/d"#);
    }

    #[test]
    fn leading_double_dash_is_dropped() {
        assert_eq!(join(&v(&["--", "claude"])), "claude");
        assert_eq!(join(&v(&["--"])), "");
        assert_eq!(join(&v(&[])), "");
    }
}
