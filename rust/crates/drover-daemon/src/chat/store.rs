//! Chats on disk: one `<id>.json` (settings) and one `<id>.jsonl` (transcript, one item per line, later lines win).
//! Same files as `chat_store.py`, so either daemon can read the other's chats.

use std::io::Write;
use std::path::{Path, PathBuf};

use indexmap::IndexMap;
use serde_json::Value;

pub struct ChatStore {
    folder: PathBuf,
}

impl ChatStore {
    pub fn new(folder: PathBuf) -> Self {
        let _ = std::fs::create_dir_all(&folder);
        Self { folder }
    }

    pub fn folder(&self) -> &Path {
        &self.folder
    }

    pub fn list_meta(&self) -> Vec<Value> {
        let mut paths: Vec<PathBuf> = std::fs::read_dir(&self.folder).into_iter().flatten().flatten()
            .map(|e| e.path())
            .filter(|p| p.extension().is_some_and(|e| e == "json"))
            .collect();
        paths.sort();
        paths.iter().filter_map(|p| {
            let meta = std::fs::read_to_string(p).ok().and_then(|t| serde_json::from_str::<Value>(&t).ok());
            if meta.is_none() {
                crate::log::warn(&format!("skipping unreadable chat file {}", p.display()));
            }
            meta.filter(|m| m["id"].is_string())
        }).collect()
    }

    pub fn save_meta(&self, meta: &Value) {
        let Some(id) = meta["id"].as_str() else { return };
        let path = self.folder.join(format!("{id}.json"));
        let tmp = path.with_extension("tmp");
        if std::fs::write(&tmp, meta.to_string()).is_ok() {
            let _ = std::fs::rename(&tmp, &path);
        }
    }

    pub fn append_item(&self, chat_id: &str, item: &Value) {
        let path = self.folder.join(format!("{chat_id}.jsonl"));
        if let Ok(mut fh) = std::fs::OpenOptions::new().create(true).append(true).open(path) {
            let _ = writeln!(fh, "{item}");
        }
    }

    pub fn load_items(&self, chat_id: &str) -> Vec<Value> {
        let Ok(text) = std::fs::read_to_string(self.folder.join(format!("{chat_id}.jsonl"))) else { return vec![] };
        let mut items: IndexMap<String, Value> = IndexMap::new();
        for line in text.lines() {
            // A half-written last line after a crash is skipped.
            if let Ok(item) = serde_json::from_str::<Value>(line)
                && let Some(id) = item["id"].as_str()
            {
                items.insert(id.to_string(), item);
            }
        }
        items.into_values().collect()
    }

    pub fn delete(&self, chat_id: &str) {
        for suffix in ["json", "jsonl"] {
            let _ = std::fs::remove_file(self.folder.join(format!("{chat_id}.{suffix}")));
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn later_lines_win_and_broken_lines_are_skipped() {
        let dir = std::env::temp_dir().join(format!("drover-chat-store-{}", crate::chat::new_id()));
        let store = ChatStore::new(dir.clone());
        store.save_meta(&json!({"id": "c1", "name": "a"}));
        store.append_item("c1", &json!({"id": "x", "text": "one"}));
        store.append_item("c1", &json!({"id": "y", "text": "two"}));
        store.append_item("c1", &json!({"id": "x", "text": "three"}));
        std::fs::OpenOptions::new().append(true).open(dir.join("c1.jsonl")).unwrap().write_all(b"{\"id\": \"z\"").unwrap();
        let items = store.load_items("c1");
        assert_eq!(items, vec![json!({"id": "x", "text": "three"}), json!({"id": "y", "text": "two"})]);
        assert_eq!(store.list_meta(), vec![json!({"id": "c1", "name": "a"})]);
        store.delete("c1");
        assert!(store.list_meta().is_empty() && store.load_items("c1").is_empty());
        let _ = std::fs::remove_dir_all(dir);
    }
}
