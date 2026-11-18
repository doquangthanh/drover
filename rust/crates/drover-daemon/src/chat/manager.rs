//! All chats of this daemon: create, find, list, remove; restores the saved ones on start. Port of `chat_manager.py`.

use std::sync::{Arc, Mutex, Weak};

use indexmap::IndexMap;
use serde_json::{Value, json};

use drover_core::status_tracker::now_secs;

use super::session::{ChatSession, PERMISSION_MODES};
use super::store::ChatStore;
use crate::event_hub::EventHub;

pub struct ChatManager {
    store: Arc<ChatStore>,
    hub: Arc<EventHub>,
    chats: Mutex<IndexMap<String, Arc<ChatSession>>>,
    me: Weak<ChatManager>,
}

impl ChatManager {
    pub fn new(folder: std::path::PathBuf, hub: Arc<EventHub>) -> Arc<Self> {
        Arc::new_cyclic(|me: &Weak<Self>| {
            let manager = Self { store: Arc::new(ChatStore::new(folder)), hub, chats: Default::default(), me: me.clone() };
            for meta in manager.store.list_meta() {
                let chat = manager.session(meta);
                manager.chats.lock().unwrap().insert(chat.id.clone(), chat);
            }
            manager
        })
    }

    fn session(&self, meta: Value) -> Arc<ChatSession> {
        let me = self.me.clone();
        let on_change = Arc::new(move || if let Some(m) = me.upgrade() { m.changed() });
        ChatSession::new(meta, self.store.clone(), self.hub.clone(), on_change)
    }

    pub fn changed(&self) {
        self.hub.emit("chats", self.snapshot());
    }

    pub fn snapshot(&self) -> Value {
        let mut all: Vec<Value> = self.chats.lock().unwrap().values().map(|c| c.to_public()).collect();
        all.sort_by(|a, b| a["updated_at"].as_f64().unwrap_or(0.0).total_cmp(&b["updated_at"].as_f64().unwrap_or(0.0)));
        json!(all)
    }

    pub fn get(&self, chat_id: &str) -> Result<Arc<ChatSession>, String> {
        self.chats.lock().unwrap().get(chat_id).cloned().ok_or_else(|| format!("no such chat: {chat_id}"))
    }

    pub fn create(&self, cwd: &str, name: Option<&str>, model: Option<&str>, permission_mode: &str,
                  space_id: Option<&str>) -> Result<Arc<ChatSession>, String> {
        let path = std::path::Path::new(cwd);
        if cwd.is_empty() || !path.is_dir() {
            return Err(format!("not a folder: {cwd}"));
        }
        if !PERMISSION_MODES.contains(&permission_mode) {
            return Err(format!("unknown permission mode: {permission_mode}"));
        }
        let resolved = std::fs::canonicalize(path).unwrap_or_else(|_| path.to_path_buf());
        let folder_name = resolved.file_name().map(|n| n.to_string_lossy().to_string()).filter(|n| !n.is_empty());
        let name: String = name.filter(|n| !n.is_empty()).map(String::from).or(folder_name).unwrap_or_else(|| "chat".into())
            .chars().take(60).collect();
        let mut chats = self.chats.lock().unwrap();
        let number = 1 + chats.keys().filter_map(|c| c.strip_prefix('c')?.parse::<u64>().ok()).max().unwrap_or(0);
        let now = now_secs();
        let meta = json!({"id": format!("c{number}"), "name": name, "cwd": resolved.to_string_lossy(), "space_id": space_id,
                          "model": model, "permission_mode": permission_mode, "session_id": null,
                          "created_at": now, "updated_at": now});
        self.store.save_meta(&meta);
        let chat = self.session(meta);
        chats.insert(chat.id.clone(), chat.clone());
        drop(chats);
        self.changed();
        Ok(chat)
    }

    pub fn rename(&self, chat_id: &str, name: &str) -> Result<(), String> {
        let chat = self.get(chat_id)?;
        chat.meta.lock().unwrap()["name"] = json!(name.chars().take(60).collect::<String>());
        chat.save_meta();
        self.changed();
        Ok(())
    }

    pub async fn remove(&self, chat_id: &str) -> Result<(), String> {
        let chat = self.get(chat_id)?;
        chat.close().await;
        self.chats.lock().unwrap().shift_remove(chat_id);
        self.store.delete(chat_id);
        self.changed();
        Ok(())
    }

    pub async fn shutdown(&self) {
        let all: Vec<Arc<ChatSession>> = self.chats.lock().unwrap().values().cloned().collect();
        for chat in all {
            chat.close().await;
        }
    }
}
