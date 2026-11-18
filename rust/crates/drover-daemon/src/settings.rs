//! settings.toml with bundled defaults and hot reload. Port of `config/settings_loader.py`.

use std::path::PathBuf;
use std::time::SystemTime;

use serde_json::{Value, json};

pub const DEFAULT_SETTINGS_TOML: &str = include_str!("default_settings.toml");

pub fn default_settings() -> Value {
    json!({
        "theme": "dark",
        "file_icons": "material",
        "prefix": "C-a",
        "tui_prefix": "C-b",
        "scrollback": 5000,
        "claude_subagent_hooks": true,
        "shell": "",
        "fs_roots": [],
        "notify": {
            "blocked": ["toast", "desktop", "sound"],
            "done": ["toast", "desktop"],
            "exited": ["toast", "desktop"],
            "quiet_hours": "",
        },
        "orchestration": {
            "max_panes": 0,
            "max_depth": 3,
            "agents_may_answer_permission_prompts": "ask-user",
            "kill_children_on_parent_exit": false,
        },
        "agents": {
            "claude": {"command": "claude", "resume": "claude --continue"},
            "codex": {"command": "codex", "resume": "codex resume --last"},
            "gemini": {"command": "gemini", "resume": "gemini --resume"},
            "opencode": {"command": "opencode", "resume": "opencode --continue"},
        },
    })
}

pub fn deep_merge(base: &Value, over: &Value) -> Value {
    match (base, over) {
        (Value::Object(b), Value::Object(o)) => {
            let mut out = b.clone();
            for (k, v) in o {
                let merged = match out.get(k) {
                    Some(existing) if existing.is_object() && v.is_object() => deep_merge(existing, v),
                    _ => v.clone(),
                };
                out.insert(k.clone(), merged);
            }
            Value::Object(out)
        }
        _ => over.clone(),
    }
}

/// TOML text -> JSON value (dates become strings).
pub fn toml_to_json(text: &str) -> Result<Value, String> {
    let table: toml::Table = toml::from_str(text).map_err(|e| e.to_string())?;
    serde_json::to_value(table).map_err(|e| e.to_string())
}

pub struct Settings {
    pub path: PathBuf,
    mtime: Option<SystemTime>,
    pub data: Value,
    pub errors: Vec<String>,
}

impl Settings {
    pub fn load(dir: PathBuf) -> Settings {
        let path = dir.join("settings.toml");
        if !path.exists() {
            let _ = std::fs::write(&path, DEFAULT_SETTINGS_TOML);
        }
        let agents_md = dir.join("AGENTS.md");
        if !agents_md.exists() {
            let _ = std::fs::write(&agents_md, include_str!("config_agents_doc.md"));
        }
        let mut s = Settings { path, mtime: None, data: default_settings(), errors: vec![] };
        s.reload_if_changed();
        s
    }

    /// Re-read settings.toml when its mtime changed. True when it was re-read.
    pub fn reload_if_changed(&mut self) -> bool {
        let Ok(mtime) = std::fs::metadata(&self.path).and_then(|m| m.modified()) else { return false };
        if self.mtime == Some(mtime) {
            return false;
        }
        self.mtime = Some(mtime);
        self.errors.clear();
        match std::fs::read_to_string(&self.path).map_err(|e| e.to_string()).and_then(|t| toml_to_json(&t)) {
            Ok(user) => self.data = deep_merge(&default_settings(), &user),
            Err(e) => self.errors.push(format!("settings.toml: {e}")),
        }
        true
    }

    pub fn get(&self, dotted: &str) -> Option<&Value> {
        dotted.split('.').try_fold(&self.data, |node, part| node.get(part))
    }

    pub fn str(&self, dotted: &str, default: &str) -> String {
        self.get(dotted).and_then(Value::as_str).unwrap_or(default).to_string()
    }

    pub fn bool(&self, dotted: &str, default: bool) -> bool {
        self.get(dotted).and_then(Value::as_bool).unwrap_or(default)
    }

    pub fn int(&self, dotted: &str, default: i64) -> i64 {
        self.get(dotted).and_then(|v| v.as_i64().or_else(|| v.as_f64().map(|f| f as i64))).unwrap_or(default)
    }

    pub fn value(&self, dotted: &str) -> Value {
        self.get(dotted).cloned().unwrap_or(Value::Null)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn user_values_merge_over_defaults() {
        let user = toml_to_json("theme = \"light\"\n[notify]\ndone = []\n").unwrap();
        let merged = deep_merge(&default_settings(), &user);
        assert_eq!(merged["theme"], "light");
        assert_eq!(merged["notify"]["done"], json!([]));
        assert_eq!(merged["notify"]["blocked"], json!(["toast", "desktop", "sound"]));
    }

    #[test]
    fn default_toml_parses() {
        assert!(toml_to_json(DEFAULT_SETTINGS_TOML).is_ok());
    }
}
