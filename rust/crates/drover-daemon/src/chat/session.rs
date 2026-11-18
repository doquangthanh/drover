//! One chat: drives a Claude conversation through the `claude` CLI and turns what comes back into transcript items.
//! Port of `chat_session.py`. A turn: `send` -> user item, then a task feeds the CLI's messages through the
//! transcript until the `result` message. Permission questions become a pending `permission` item and wait for
//! `answer` (see `session_permissions.rs`).

use std::collections::HashMap;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use serde_json::{Value, json};
use tokio::sync::oneshot;

use drover_core::status_tracker::now_secs;

use super::cli_process::{ClaudeCli, CliOptions, Incoming};
use super::store::ChatStore;
use super::transcript::Transcript;
use crate::event_hub::EventHub;

pub const PERMISSION_MODES: [&str; 4] = ["default", "acceptEdits", "plan", "bypassPermissions"];
const CONTROL_TIMEOUT: Duration = Duration::from_secs(60);

pub struct ChatSession {
    pub id: String,
    pub(super) meta: Mutex<Value>,
    pub(super) transcript: Mutex<Transcript>,
    state: Mutex<&'static str>, // idle | working | blocked
    cli: tokio::sync::Mutex<Option<Arc<ClaudeCli>>>,
    /// Permission item id -> (CLI request id, where the user's (allow, always) goes).
    pub(super) pending: Mutex<HashMap<String, (String, oneshot::Sender<(bool, bool)>)>>,
    info: Mutex<Option<Value>>,
    task: Mutex<Option<tokio::task::JoinHandle<()>>>,
    store: Arc<ChatStore>,
    hub: Arc<EventHub>,
    on_change: Arc<dyn Fn() + Send + Sync>,
}

impl ChatSession {
    pub fn new(meta: Value, store: Arc<ChatStore>, hub: Arc<EventHub>, on_change: Arc<dyn Fn() + Send + Sync>) -> Arc<Self> {
        let id = meta["id"].as_str().unwrap_or_default().to_string();
        let transcript = Transcript::new(store.load_items(&id));
        Arc::new(Self { id, meta: Mutex::new(meta), transcript: Mutex::new(transcript), state: Mutex::new("idle"),
                        cli: Default::default(), pending: Default::default(), info: Mutex::new(None),
                        task: Mutex::new(None), store, hub, on_change })
    }

    pub fn items(&self) -> Vec<Value> {
        self.transcript.lock().unwrap().items.values().cloned().collect()
    }

    pub fn state(&self) -> &'static str {
        *self.state.lock().unwrap()
    }

    pub fn to_public(&self) -> Value {
        let m = self.meta.lock().unwrap();
        json!({"id": m["id"], "name": m["name"], "cwd": m["cwd"], "space_id": m["space_id"], "state": self.state(),
               "permission_mode": m["permission_mode"], "model": m["model"], "updated_at": m["updated_at"]})
    }

    pub fn cwd(&self) -> String {
        self.meta.lock().unwrap()["cwd"].as_str().unwrap_or_default().to_string()
    }

    pub(super) fn save_meta(&self) {
        self.store.save_meta(&self.meta.lock().unwrap());
    }

    // ---- output ---------------------------------------------------------------------------------------------
    pub(super) fn emit(&self, ops: Vec<Value>) {
        for mut op in ops {
            if op["op"] == "session" {
                {
                    let mut m = self.meta.lock().unwrap();
                    for k in ["session_id", "model"] {
                        if op[k].as_str().is_some_and(|v| !v.is_empty()) {
                            m[k] = op[k].clone();
                        }
                    }
                }
                self.save_meta();
                continue;
            }
            if op["op"] == "item" && op["item"]["live"] != true {
                self.store.append_item(&self.id, &op["item"]);
            }
            op["chat"] = json!(self.id);
            self.hub.emit("chat", op);
        }
    }

    pub(super) fn set_state(&self, state: &'static str) {
        if std::mem::replace(&mut *self.state.lock().unwrap(), state) == state {
            return;
        }
        self.meta.lock().unwrap()["updated_at"] = json!(now_secs());
        self.save_meta();
        (self.on_change)();
    }

    // ---- input ----------------------------------------------------------------------------------------------
    /// Start a turn; Err when the previous one is still running.
    pub fn send(self: &Arc<Self>, text: &str, images: &[Value]) -> Result<(), String> {
        if self.state() != "idle" {
            return Err("The agent is still working on the previous message.".into());
        }
        let ops = self.transcript.lock().unwrap().user(text, &json!(images));
        self.emit(ops);
        let mut content: Vec<Value> = images.iter()
            .map(|i| json!({"type": "image", "source": {"type": "base64", "media_type": i["media_type"], "data": i["data"]}}))
            .collect();
        if !text.is_empty() {
            content.push(json!({"type": "text", "text": text}));
        }
        self.set_state("working");
        let me = self.clone();
        *self.task.lock().unwrap() = Some(tokio::spawn(async move { me.turn(json!(content)).await }));
        Ok(())
    }

    async fn turn(self: Arc<Self>, content: Value) {
        if let Err(e) = self.clone().run_turn(content).await {
            crate::log::warn(&format!("chat {} failed: {e}", self.id));
            let ops = self.transcript.lock().unwrap().notice(&format!("The agent stopped: {e}"), "error");
            self.emit(ops);
            self.drop_cli().await;
        }
        let ops = self.transcript.lock().unwrap().finish_turn();
        self.emit(ops);
        self.set_state("idle");
    }

    async fn run_turn(self: Arc<Self>, content: Value) -> Result<(), String> {
        let cli = self.ensure_cli().await?;
        cli.send_user(content)?;
        let mut incoming = cli.incoming.lock().await;
        loop {
            match incoming.recv().await {
                None => return Err(format!("the agent process has exited{}", cli.stderr_hint())),
                Some(Incoming::Message(msg)) => {
                    let ops = self.transcript.lock().unwrap().feed(&msg);
                    self.emit(ops);
                    if msg["type"] == "result" {
                        return Ok(());
                    }
                }
                Some(Incoming::Permission { request_id, request }) => {
                    tokio::spawn(self.clone().permission(cli.clone(), request_id, request));
                }
                Some(Incoming::Cancel(request_id)) => self.cancel_permission(&request_id),
            }
        }
    }

    async fn ensure_cli(&self) -> Result<Arc<ClaudeCli>, String> {
        let mut slot = self.cli.lock().await;
        if let Some(cli) = slot.as_ref() {
            return Ok(cli.clone());
        }
        let exe = super::locator::find_claude()
            .ok_or("the claude command was not found (install Claude Code, or add it to PATH)")?;
        let opts = {
            let m = self.meta.lock().unwrap();
            let text = |k: &str| m[k].as_str().filter(|v| !v.is_empty()).map(String::from);
            CliOptions { exe, cwd: text("cwd").unwrap_or_else(|| ".".into()), permission_mode: text("permission_mode").unwrap_or_else(|| "default".into()),
                         model: text("model"), resume: text("session_id") }
        };
        let cli = ClaudeCli::spawn(&opts).await?;
        *slot = Some(cli.clone());
        Ok(cli)
    }

    async fn current_cli(&self) -> Option<Arc<ClaudeCli>> {
        self.cli.lock().await.clone()
    }

    /// Slash commands and models the CLI offers. Starts the CLI the first time, then answers from memory.
    pub async fn options(&self) -> Result<Value, String> {
        if let Some(info) = self.info.lock().unwrap().clone() {
            return Ok(info);
        }
        let raw = self.ensure_cli().await?.info.clone();
        let list = |k: &str| raw[k].as_array().cloned().unwrap_or_default();
        let info = json!({
            "commands": list("commands").iter().filter(|c| c["name"].as_str().is_some_and(|n| !n.is_empty())).map(|c| json!({
                "name": c["name"], "description": c["description"].as_str().unwrap_or_default(),
                "hint": c["argumentHint"].as_str().unwrap_or_default()})).collect::<Vec<_>>(),
            "models": list("models").iter().filter(|m| m["value"].as_str().is_some_and(|v| !v.is_empty())).map(|m| json!({
                "value": m["value"], "label": m["displayName"].as_str().filter(|l| !l.is_empty()).map_or(m["value"].clone(), |l| json!(l)),
                "description": m["description"].as_str().unwrap_or_default()})).collect::<Vec<_>>(),
        });
        *self.info.lock().unwrap() = Some(info.clone());
        Ok(info)
    }

    /// `default` (or empty) means the CLI's own choice.
    pub async fn set_model(&self, model: &str) -> Result<(), String> {
        let value = if model.is_empty() || model == "default" { Value::Null } else { json!(model) };
        self.meta.lock().unwrap()["model"] = value.clone();
        self.save_meta();
        if let Some(cli) = self.current_cli().await {
            cli.control(json!({"subtype": "set_model", "model": value}), CONTROL_TIMEOUT).await?;
        }
        (self.on_change)();
        Ok(())
    }

    pub async fn set_permission_mode(&self, mode: &str) -> Result<(), String> {
        self.meta.lock().unwrap()["permission_mode"] = json!(mode);
        self.save_meta();
        if let Some(cli) = self.current_cli().await {
            cli.control(json!({"subtype": "set_permission_mode", "mode": mode}), CONTROL_TIMEOUT).await?;
        }
        Ok(())
    }

    pub async fn interrupt(&self) -> Result<(), String> {
        self.deny_all_pending();
        if self.state() != "idle"
            && let Some(cli) = self.current_cli().await
        {
            cli.control(json!({"subtype": "interrupt"}), CONTROL_TIMEOUT).await?;
        }
        Ok(())
    }

    async fn drop_cli(&self) {
        *self.info.lock().unwrap() = None;
        self.cli.lock().await.take(); // dropping the last handle kills the process
    }

    pub async fn close(&self) {
        self.deny_all_pending();
        if let Some(task) = self.task.lock().unwrap().take() {
            task.abort();
        }
        self.drop_cli().await;
    }
}

#[cfg(test)]
#[path = "session_tests.rs"]
mod tests;
