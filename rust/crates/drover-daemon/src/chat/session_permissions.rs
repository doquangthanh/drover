//! Permission questions of a chat: the CLI's `can_use_tool` request becomes a pending `permission` item; the user's
//! `chat.answer` (or an interrupt, or the CLI cancelling) settles it. Port of `_can_use_tool` / `answer`.

use std::sync::Arc;

use serde_json::{Value, json};
use tokio::sync::oneshot;

use super::cli_process::ClaudeCli;
use super::new_id;
use super::session::ChatSession;

impl ChatSession {
    pub(super) async fn permission(self: Arc<Self>, cli: Arc<ClaudeCli>, request_id: String, request: Value) {
        if request["subtype"] != "can_use_tool" {
            let what = request["subtype"].as_str().unwrap_or("?");
            let _ = cli.respond_error(&request_id, &format!("Unsupported control request subtype: {what}"));
            return;
        }
        let mut item = json!({"id": new_id(), "kind": "permission", "tool": request["tool_name"], "input": request["input"],
                              "status": "pending", "title": request["title"], "detail": request["description"]});
        let item_id = item["id"].as_str().unwrap_or_default().to_string();
        let (tx, rx) = oneshot::channel();
        self.pending.lock().unwrap().insert(item_id.clone(), (request_id.clone(), tx));
        let ops = self.transcript.lock().unwrap().put(item.clone());
        self.emit(ops);
        self.set_state("blocked");
        let answer = rx.await; // Err: the CLI cancelled the question (no reply expected then)
        self.pending.lock().unwrap().remove(&item_id);
        let cancelled = answer.is_err();
        let (allow, always) = answer.unwrap_or((false, false));
        item["status"] = json!(if allow { "allowed" } else { "denied" });
        let ops = self.transcript.lock().unwrap().put(item);
        self.emit(ops);
        if self.state() == "blocked" && self.pending.lock().unwrap().is_empty() {
            self.set_state("working");
        }
        if cancelled {
            return;
        }
        let response = if !allow {
            json!({"behavior": "deny", "message": "The user denied this action."})
        } else {
            let mut r = json!({"behavior": "allow", "updatedInput": request["input"]});
            let suggestions = request["permission_suggestions"].as_array().cloned().unwrap_or_default();
            if always && !suggestions.is_empty() {
                r["updatedPermissions"] = json!(suggestions);
            }
            r
        };
        let _ = cli.respond(&request_id, response);
    }

    /// The user's answer to permission item `request`; false when nothing waits for it.
    pub fn answer(&self, request: &str, allow: bool, always: bool) -> bool {
        match self.pending.lock().unwrap().remove(request) {
            Some((_, tx)) => tx.send((allow, always)).is_ok(),
            None => false,
        }
    }

    pub(super) fn cancel_permission(&self, request_id: &str) {
        self.pending.lock().unwrap().retain(|_, (r, _)| r != request_id); // dropped sender = cancelled
    }

    pub(super) fn deny_all_pending(&self) {
        for (_, (_, tx)) in self.pending.lock().unwrap().drain() {
            let _ = tx.send((false, false));
        }
    }
}
