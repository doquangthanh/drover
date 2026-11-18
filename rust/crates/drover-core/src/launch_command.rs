//! Launch commands: split like the Python daemon and map to an agent id.

use std::path::Path;

use crate::detection_rules::AgentRuleSet;

/// Split a launch command like the Python daemon: POSIX shell rules, or on Windows literal backslashes with the
/// surrounding quotes of each token dropped.
pub fn split_command(command: &str) -> Option<Vec<String>> {
    if cfg!(windows) { Some(split_windows(command)) } else { shlex::split(command) }
}

fn split_windows(command: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut cur = String::new();
    let mut quote: Option<char> = None;
    for ch in command.chars() {
        match (quote, ch) {
            (Some(q), c) if c == q => quote = None,
            (Some(_), c) => cur.push(c),
            (None, '"' | '\'') => quote = Some(ch),
            (None, c) if c.is_whitespace() => {
                if !cur.is_empty() {
                    out.push(std::mem::take(&mut cur));
                }
            }
            (None, c) => cur.push(c),
        }
    }
    if !cur.is_empty() {
        out.push(cur);
    }
    out
}

/// Map a launch command like `C:/.../claude.cmd --continue` to an agent id ("shell" when unknown).
pub fn match_agent_kind(command: &str, sets: &[AgentRuleSet]) -> String {
    let tokens = split_command(command).unwrap_or_else(|| command.split_whitespace().map(String::from).collect());
    let Some(first) = tokens.first() else { return "shell".into() };
    let first = first.replace('\\', "/");
    let stem = Path::new(&first).file_stem().and_then(|s| s.to_str()).unwrap_or("").to_lowercase();
    sets.iter()
        .find(|s| s.names().any(|n| n.to_lowercase() == stem))
        .map(|s| s.id.clone())
        .unwrap_or_else(|| "shell".into())
}
