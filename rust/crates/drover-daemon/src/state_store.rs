//! session.json: layout + pane metadata so a restarted daemon can offer to resume agents. Port of `state_store.py`.

use std::path::PathBuf;

use serde_json::{Map, Value};

pub struct StateStore {
    pub path: PathBuf,
}

impl StateStore {
    pub fn load(&self) -> Map<String, Value> {
        match std::fs::read_to_string(&self.path) {
            Ok(text) => serde_json::from_str::<Value>(&text)
                .ok()
                .and_then(|v| v.as_object().cloned())
                .unwrap_or_else(|| {
                    crate::log::warn(&format!("ignoring unreadable session file {}", self.path.display()));
                    Map::new()
                }),
            Err(_) => Map::new(),
        }
    }

    /// Atomic write: temp file in the same folder, then rename over the old one.
    pub fn save(&self, data: &Value) {
        let Some(dir) = self.path.parent() else { return };
        let _ = std::fs::create_dir_all(dir);
        let tmp = dir.join(format!("session-{}.json.tmp", std::process::id()));
        let result = serde_json::to_vec_pretty(data)
            .map_err(std::io::Error::other)
            .and_then(|bytes| std::fs::write(&tmp, bytes))
            .and_then(|_| std::fs::rename(&tmp, &self.path));
        if let Err(e) = result {
            crate::log::warn(&format!("could not save session: {e}"));
            let _ = std::fs::remove_file(&tmp);
        }
    }
}
