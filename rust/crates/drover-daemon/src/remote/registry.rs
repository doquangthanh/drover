//! machines.toml: remote machines reached over SSH. Port of `machine_registry.py` (same file format).

use indexmap::IndexMap;

#[derive(Clone, Debug, PartialEq)]
pub struct Machine {
    pub alias: String,
    /// user@host or a `~/.ssh/config` Host
    pub target: String,
    pub port: u16,
    /// optional identity file; empty = ssh-agent / default keys
    pub key: String,
    /// verify host keys
    pub known_hosts: bool,
}

impl Machine {
    pub fn new(alias: &str, target: &str) -> Self {
        Self { alias: alias.into(), target: target.into(), port: 22, key: String::new(), known_hosts: true }
    }
}

fn alias_ok(alias: &str) -> bool {
    let mut chars = alias.chars();
    chars.next().is_some_and(|c| c.is_ascii_lowercase() || c.is_ascii_digit())
        && alias.len() <= 32
        && chars.all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '_' || c == '-')
}

pub fn machines_file() -> std::path::PathBuf {
    crate::paths::config_dir().join("machines.toml")
}

pub fn load_machines() -> IndexMap<String, Machine> {
    let text = std::fs::read_to_string(machines_file()).unwrap_or_default();
    let raw: toml::Table = text.parse().unwrap_or_default();
    let mut out = IndexMap::new();
    for (alias, item) in raw.get("machines").and_then(|m| m.as_table()).into_iter().flatten() {
        let Some(item) = item.as_table() else { continue };
        let Some(target) = item.get("target").and_then(|t| t.as_str()).filter(|t| !t.is_empty()) else { continue };
        if !alias_ok(alias) {
            continue;
        }
        out.insert(alias.clone(), Machine {
            alias: alias.clone(), target: target.into(),
            port: item.get("port").and_then(|p| p.as_integer()).and_then(|p| u16::try_from(p).ok()).unwrap_or(22),
            key: item.get("key").and_then(|k| k.as_str()).unwrap_or_default().into(),
            known_hosts: item.get("known_hosts").and_then(|k| k.as_bool()).unwrap_or(true),
        });
    }
    out
}

fn quote(value: &str) -> String {
    format!("\"{}\"", value.replace('\\', "\\\\").replace('"', "\\\""))
}

pub fn save_machines(machines: &IndexMap<String, Machine>) -> std::io::Result<()> {
    let mut lines = vec!["# Remote machines for drover. Edit freely; drover reconnects on save.".to_string(), String::new()];
    for m in machines.values() {
        lines.push(format!("[machines.{}]", m.alias));
        lines.push(format!("target = {}", quote(&m.target)));
        if m.port != 22 {
            lines.push(format!("port = {}", m.port));
        }
        if !m.key.is_empty() {
            lines.push(format!("key = {}", quote(&m.key)));
        }
        if !m.known_hosts {
            lines.push("known_hosts = false".into());
        }
        lines.push(String::new());
    }
    std::fs::write(machines_file(), lines.join("\n"))
}

pub fn validate_new(alias: &str, target: &str, existing: &IndexMap<String, Machine>) -> Result<(), String> {
    if !alias_ok(alias) || ["local", "self", "this"].contains(&alias) {
        return Err("name: lowercase letters, digits, - or _, max 32 chars".into());
    }
    let mut chars = alias.chars();
    if chars.next().is_some_and(|c| "sta".contains(c)) && alias.len() > 1 && chars.all(|c| c.is_ascii_digit()) {
        return Err("name looks like an internal id (s1, t3, a2…); pick another".into());
    }
    if existing.contains_key(alias) {
        return Err(format!("machine '{alias}' already exists"));
    }
    if target.is_empty() || target.chars().any(char::is_whitespace) || target.starts_with('-') {
        return Err("target must look like user@host".into());
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn validation_matches_python() {
        assert!(validate_new("vps-1", "alice@10.0.0.5", &IndexMap::new()).is_ok());
        let long = "a".repeat(33);
        for alias in ["Local", "local", "self", "this", "VPS", "-x", long.as_str(), "has space", ""] {
            assert!(validate_new(alias, "user@host", &IndexMap::new()).unwrap_err().starts_with("name:"), "{alias}");
        }
        assert!(validate_new("s1", "u@h", &IndexMap::new()).unwrap_err().contains("internal id"));
        let existing: IndexMap<String, Machine> = [("vps-1".to_string(), Machine::new("vps-1", "alice@10.0.0.5"))].into();
        assert!(validate_new("vps-1", "bob@host", &existing).unwrap_err().contains("already exists"));
        for target in ["", "user name@host", "-oProxyCommand=x"] {
            assert!(validate_new("vps-2", target, &existing).unwrap_err().contains("target"));
        }
    }
}
