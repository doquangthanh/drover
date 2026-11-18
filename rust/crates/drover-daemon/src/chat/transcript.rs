//! claude CLI stream-json messages -> transcript items. Port of `transcript_builder.py` (same items and ops, so the
//! chat view and saved chats work with either daemon).
//!
//! Items (keyed by `id`): user {text, images}, text/thinking {text, live}, tool {name, input, status, result,
//! is_error, parent?}, permission (built by the session), result {ok, ms, cost, turns, error}, notice {text, level}.
//! Ops for the UI: {"op":"item","item"} (upsert by id), {"op":"delta","id","text"}, and {"op":"session"} (kept by
//! the session, never sent).

use std::collections::BTreeMap;

use indexmap::IndexMap;
use serde_json::{Value, json};

use super::new_id;

pub const MAX_RESULT_CHARS: usize = 20_000;

/// A tool result as plain text (blocks joined, images as a marker), cut to a sane size.
pub fn result_text(content: &Value) -> String {
    let text = match content {
        Value::String(s) => s.clone(),
        Value::Null => String::new(),
        Value::Array(blocks) => blocks.iter().map(|b| match b {
            Value::Object(o) => o.get("text").and_then(Value::as_str).unwrap_or("[image]").to_string(),
            other => other.to_string(),
        }).collect::<Vec<_>>().join("\n"),
        other => other.to_string(),
    };
    let count = text.chars().count();
    if count <= MAX_RESULT_CHARS {
        return text;
    }
    let cut: String = text.chars().take(MAX_RESULT_CHARS).collect();
    format!("{cut}\n… ({} more characters)", count - MAX_RESULT_CHARS)
}

#[derive(Default)]
pub struct Transcript {
    pub items: IndexMap<String, Value>,
    live: BTreeMap<i64, String>, // stream block index -> id of the item being streamed
}

fn item_op(item: &Value) -> Value {
    json!({"op": "item", "item": item})
}

impl Transcript {
    pub fn new(items: Vec<Value>) -> Self {
        let items = items.into_iter().filter_map(|i| Some((i["id"].as_str()?.to_string(), i))).collect();
        Self { items, live: BTreeMap::new() }
    }

    pub fn put(&mut self, item: Value) -> Vec<Value> {
        let op = item_op(&item);
        self.items.insert(item["id"].as_str().unwrap_or_default().to_string(), item);
        vec![op]
    }

    pub fn user(&mut self, text: &str, images: &Value) -> Vec<Value> {
        self.put(json!({"id": new_id(), "kind": "user", "text": text, "images": images}))
    }

    pub fn notice(&mut self, text: &str, level: &str) -> Vec<Value> {
        self.put(json!({"id": new_id(), "kind": "notice", "text": text, "level": level}))
    }

    pub fn feed(&mut self, msg: &Value) -> Vec<Value> {
        match msg["type"].as_str() {
            Some("stream_event") => self.stream(&msg["event"]),
            Some("assistant") => self.assistant(msg),
            Some("user") => self.tool_results(msg),
            Some("result") => self.result(msg),
            Some("system") if msg["subtype"] == "init" => {
                vec![json!({"op": "session", "session_id": msg["session_id"], "model": msg["model"]})]
            }
            _ => vec![],
        }
    }

    /// Anything still running when a turn ends was interrupted.
    pub fn finish_turn(&mut self) -> Vec<Value> {
        let mut ops = vec![];
        for item in self.items.values_mut() {
            if item["kind"] == "tool" && item["status"] == "running" {
                item["status"] = json!("stopped");
                ops.push(item_op(item));
            } else if item["live"] == true {
                item["live"] = json!(false);
                ops.push(item_op(item));
            }
        }
        self.live.clear();
        ops
    }

    fn stream(&mut self, ev: &Value) -> Vec<Value> {
        match ev["type"].as_str() {
            Some("message_start") => self.live.clear(),
            Some("content_block_start") => {
                let kind = ev["content_block"]["type"].as_str().unwrap_or_default();
                if kind == "text" || kind == "thinking" {
                    let id = new_id();
                    self.live.insert(ev["index"].as_i64().unwrap_or(0), id.clone());
                    return self.put(json!({"id": id, "kind": kind, "text": "", "live": true}));
                }
            }
            Some("content_block_delta") => {
                let delta = &ev["delta"];
                let text = [&delta["text"], &delta["thinking"]].into_iter()
                    .filter_map(Value::as_str).find(|t| !t.is_empty()).unwrap_or_default();
                let id = ev["index"].as_i64().and_then(|i| self.live.get(&i)).cloned().unwrap_or_default();
                if let Some(item) = self.items.get_mut(&id)
                    && !text.is_empty()
                {
                    let joined = format!("{}{text}", item["text"].as_str().unwrap_or_default());
                    item["text"] = json!(joined);
                    return vec![json!({"op": "delta", "id": id, "text": text})];
                }
            }
            _ => {}
        }
        vec![]
    }

    fn take_live(&mut self, kind: &str) -> Option<Value> {
        let index = *self.live.iter().find(|(_, id)| {
            self.items.get(*id).is_some_and(|i| i["kind"] == kind && i["live"] == true)
        })?.0;
        let id = self.live.remove(&index)?;
        self.items.get(&id).cloned()
    }

    fn assistant(&mut self, msg: &Value) -> Vec<Value> {
        let mut ops = vec![];
        let parent = msg["parent_tool_use_id"].as_str().filter(|p| !p.is_empty());
        for block in msg["message"]["content"].as_array().into_iter().flatten() {
            let mut item = match block["type"].as_str() {
                Some(kind @ ("text" | "thinking")) => {
                    let mut item = self.take_live(kind).unwrap_or_else(|| json!({"id": new_id(), "kind": kind}));
                    item["text"] = block[kind].clone();
                    item["live"] = json!(false);
                    item
                }
                Some("tool_use") => json!({"id": block["id"], "kind": "tool", "name": block["name"], "input": block["input"],
                                           "status": "running", "result": null, "is_error": false}),
                _ => continue,
            };
            if let Some(parent) = parent {
                item["parent"] = json!(parent);
            }
            ops.extend(self.put(item));
        }
        ops
    }

    fn tool_results(&mut self, msg: &Value) -> Vec<Value> {
        let mut ops = vec![];
        for block in msg["message"]["content"].as_array().into_iter().flatten() {
            if block["type"] != "tool_result" {
                continue;
            }
            let Some(tool) = block["tool_use_id"].as_str().and_then(|id| self.items.get_mut(id)) else { continue };
            let is_error = block["is_error"].as_bool().unwrap_or(false);
            tool["result"] = json!(result_text(&block["content"]));
            tool["is_error"] = json!(is_error);
            tool["status"] = json!(if is_error { "error" } else { "done" });
            ops.push(item_op(tool));
        }
        ops
    }

    fn result(&mut self, msg: &Value) -> Vec<Value> {
        let is_error = msg["is_error"].as_bool().unwrap_or(false);
        let error = is_error.then(|| {
            let errors: Vec<&str> = msg["errors"].as_array().into_iter().flatten().filter_map(Value::as_str).collect();
            [msg["result"].as_str().unwrap_or_default().to_string(), errors.join("; ")].into_iter()
                .find(|s| !s.is_empty()).unwrap_or_else(|| "The turn ended with an error.".into())
        });
        self.put(json!({"id": new_id(), "kind": "result", "ok": !is_error, "ms": msg["duration_ms"],
                        "cost": msg["total_cost_usd"], "turns": msg["num_turns"], "error": error}))
    }
}

#[cfg(test)]
#[path = "transcript_tests.rs"]
mod tests;
