//! In-memory log of agent-to-agent actions (spawn, wait, send, report) for the agent tree view.
//! Port of `agent_messages_log.py` and `orchestration_policy.py`.

use std::collections::{HashSet, VecDeque};

use serde_json::{Value, json};

use drover_core::status_tracker::now_secs;

const MAX_TEXT: usize = 500;
const LIMIT: usize = 500;

#[derive(Default)]
pub struct MessagesLog {
    pub items: VecDeque<Value>,
}

impl MessagesLog {
    pub fn add(&mut self, kind: &str, source: Option<&str>, target: Option<&str>, text: &str) -> Value {
        // A long prompt would otherwise sit in memory in full and go out in every messages.list reply.
        let text: String = if text.chars().count() <= MAX_TEXT {
            text.to_string()
        } else {
            text.chars().take(MAX_TEXT).collect::<String>() + "…"
        };
        let msg = json!({"kind": kind, "source": source, "target": target, "text": text, "at": now_secs()});
        if self.items.len() >= LIMIT {
            self.items.pop_front();
        }
        self.items.push_back(msg.clone());
        msg
    }

    /// A pane finished, exited or needs an answer: tell its parent, or you (target None) for an agent you started.
    pub fn add_state(&mut self, pane_id: &str, parent: Option<&str>, state: &str, text: &str) -> Option<Value> {
        if !matches!(state, "done" | "blocked" | "exited") {
            return None;
        }
        Some(self.add(state, Some(pane_id), parent.filter(|p| !p.is_empty()), text))
    }

    /// Messages touching the tree, including its panes' sub-agents (virtual ids `<pane>/<agent>`).
    pub fn for_tree(&self, pane_ids: &HashSet<String>) -> Vec<Value> {
        let inside = |v: &Value| {
            v.as_str().is_some_and(|a| !a.is_empty() && (pane_ids.contains(a) || pane_ids.contains(a.split('/').next().unwrap_or(""))))
        };
        self.items.iter().filter(|m| inside(&m["source"]) || inside(&m["target"])).cloned().collect()
    }
}

/// Limits on agents spawning agents, and who may answer permission prompts.
pub struct Policy {
    pub max_panes: i64,
    pub max_depth: i64,
    pub answer_prompts: String,
}

impl Policy {
    pub fn from_settings(section: &Value) -> Policy {
        let int = |k: &str, d: i64| section.get(k).and_then(|v| v.as_i64().or_else(|| v.as_f64().map(|f| f as i64))).unwrap_or(d);
        Policy {
            max_panes: int("max_panes", 0),
            max_depth: int("max_depth", 3),
            answer_prompts: section
                .get("agents_may_answer_permission_prompts")
                .and_then(Value::as_str)
                .unwrap_or("ask-user")
                .to_string(),
        }
    }

    pub fn check_spawn(&self, live_panes: usize, parent_depth: Option<i64>) -> Result<(), String> {
        if self.max_panes > 0 && live_panes as i64 >= self.max_panes {
            return Err(format!("pane limit reached ({}); close something or raise max_panes", self.max_panes));
        }
        if let Some(depth) = parent_depth
            && depth + 1 > self.max_depth
        {
            return Err(format!("agents may only nest {} levels deep", self.max_depth));
        }
        Ok(())
    }

    /// An agent (not the user) is typing into a pane that is waiting on a permission prompt.
    pub fn may_agent_answer(&self, target_state: &str) -> bool {
        target_state != "blocked" || self.answer_prompts == "always"
    }
}
