//! session.json: layout + pane metadata so a restarted daemon can offer to resume agents. Port of `state_store.py`.
//! Safety nets (Herdr's): a file that cannot be read, or comes from a newer format, is copied to `session-backups/`
//! (3 kept) before anything overwrites it; every save keeps a copy of the previous file in `session-snapshots/` at
//! most every 15 minutes (48 kept, about 12 hours). Neither is restored automatically: copy one over session.json
//! while the daemon is stopped.

use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde_json::{Map, Value};

/// Newest session format this daemon writes (`persistence::serialize`).
pub const SESSION_VERSION: u64 = 1;
const BACKUPS_KEPT: usize = 3;
const SNAPSHOTS_KEPT: usize = 48;
const SNAPSHOT_EVERY: Duration = Duration::from_secs(15 * 60);

pub struct StateStore {
    pub path: PathBuf,
}

impl StateStore {
    pub fn load(&self) -> Map<String, Value> {
        let Ok(text) = std::fs::read_to_string(&self.path) else { return Map::new() };
        match serde_json::from_str::<Value>(&text).ok().and_then(|v| v.as_object().cloned()) {
            Some(data) => {
                if data.get("version").and_then(Value::as_u64).is_some_and(|v| v > SESSION_VERSION) {
                    // Written by a newer drover: keep a copy, the next save here drops what this one doesn't know.
                    self.keep_copy("session-backups", BACKUPS_KEPT);
                }
                data
            }
            None => {
                let kept = self.keep_copy("session-backups", BACKUPS_KEPT);
                crate::log::warn(&format!("ignoring unreadable session file {} (copy: {})", self.path.display(),
                    kept.map_or("none".into(), |p| p.display().to_string())));
                Map::new()
            }
        }
    }

    /// Atomic write: temp file in the same folder, then rename over the old one.
    pub fn save(&self, data: &Value) {
        let Some(dir) = self.path.parent() else { return };
        let _ = std::fs::create_dir_all(dir);
        if self.snapshot_due() {
            self.keep_copy("session-snapshots", SNAPSHOTS_KEPT);
        }
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

    fn sibling(&self, folder: &str) -> PathBuf {
        self.path.parent().unwrap_or(Path::new(".")).join(folder)
    }

    /// The newest snapshot is older than SNAPSHOT_EVERY (or there is none) and there is a file to keep.
    fn snapshot_due(&self) -> bool {
        if !self.path.is_file() {
            return false;
        }
        let newest = copies(&self.sibling("session-snapshots")).into_iter().filter_map(|p| p.metadata().ok()?.modified().ok()).max();
        newest.is_none_or(|t| t.elapsed().is_ok_and(|age| age >= SNAPSHOT_EVERY))
    }

    /// Copy session.json to `<folder>/session-<unix ms>.json`, then drop the oldest beyond `keep`.
    fn keep_copy(&self, folder: &str, keep: usize) -> Option<PathBuf> {
        let dir = self.sibling(folder);
        std::fs::create_dir_all(&dir).ok()?;
        let ms = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis()).unwrap_or(0);
        let copy = dir.join(format!("session-{ms:015}.json"));
        let done = std::fs::copy(&self.path, &copy).ok().map(|_| copy);
        let mut all = copies(&dir);
        all.sort(); // zero-padded times: name order is age order
        for old in all.iter().take(all.len().saturating_sub(keep)) {
            let _ = std::fs::remove_file(old);
        }
        done
    }
}

fn copies(dir: &Path) -> Vec<PathBuf> {
    std::fs::read_dir(dir).into_iter().flatten().flatten().map(|e| e.path())
        .filter(|p| p.file_name().and_then(|n| n.to_str()).is_some_and(|n| n.starts_with("session-") && n.ends_with(".json")))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn store(name: &str) -> StateStore {
        let dir = std::env::temp_dir().join(format!("drover-store-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        StateStore { path: dir.join("session.json") }
    }

    #[test]
    fn a_corrupt_file_is_copied_before_it_is_replaced() {
        let s = store("corrupt");
        for _ in 0..5 {
            std::fs::write(&s.path, "{not json").unwrap();
            assert!(s.load().is_empty());
            std::thread::sleep(Duration::from_millis(2)); // distinct names
        }
        let kept = copies(&s.sibling("session-backups"));
        assert_eq!(kept.len(), BACKUPS_KEPT);
        assert_eq!(std::fs::read_to_string(&kept[0]).unwrap(), "{not json");
        let _ = std::fs::remove_dir_all(s.path.parent().unwrap());
    }

    #[test]
    fn a_newer_format_is_loaded_and_copied() {
        let s = store("newer");
        std::fs::write(&s.path, r#"{"version": 99, "panes": []}"#).unwrap();
        assert!(s.load().contains_key("panes"));
        assert_eq!(copies(&s.sibling("session-backups")).len(), 1);
        let _ = std::fs::remove_dir_all(s.path.parent().unwrap());
    }

    #[test]
    fn saves_snapshot_the_previous_file_at_most_every_interval() {
        let s = store("snap");
        s.save(&serde_json::json!({"version": 1, "n": 1})); // nothing to snapshot yet
        assert!(copies(&s.sibling("session-snapshots")).is_empty());
        s.save(&serde_json::json!({"version": 1, "n": 2}));
        s.save(&serde_json::json!({"version": 1, "n": 3})); // within 15 minutes of the first snapshot
        let snaps = copies(&s.sibling("session-snapshots"));
        assert_eq!(snaps.len(), 1);
        assert!(std::fs::read_to_string(&snaps[0]).unwrap().contains("\"n\": 1"));
        assert_eq!(s.load()["n"], 3);
        let _ = std::fs::remove_dir_all(s.path.parent().unwrap());
    }
}
