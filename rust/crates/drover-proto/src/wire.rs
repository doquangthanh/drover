//! What the daemon sends over /ws, parsed. Shapes match `Manager::snapshot` and `PaneSession::to_json`.

use serde::Deserialize;
use serde_json::Value;

pub use drover_core::layout_tree::{Dir, Node};
pub use drover_core::workspace_models::Tab;

#[derive(Debug, Clone, Default, Deserialize, PartialEq)]
#[serde(default)]
pub struct Pane {
    pub id: String,
    pub name: String,
    pub kind: String,
    pub command: String,
    pub cwd: String,
    pub space_id: String,
    pub tab_id: String,
    pub parent: Option<String>,
    pub created_at: f64,
    /// working | blocked | done | idle | exited | stopped
    pub state: String,
    pub since: f64,
    pub unread: bool,
    pub exit_code: Option<i64>,
    pub title: String,
    pub machine: String,
    pub cols: u16,
    pub rows: u16,
}

/// A space plus the git facts the daemon merges into it (branch, dirty, ahead).
#[derive(Debug, Clone, Default, Deserialize, PartialEq)]
#[serde(default)]
pub struct Space {
    pub id: String,
    pub name: String,
    pub cwd: String,
    pub color: i64,
    pub machine: Option<String>,
    pub branch: Option<String>,
    /// Number of changed files in the working tree.
    pub dirty: Option<i64>,
    pub ahead: Option<i64>,
}

#[derive(Debug, Clone, Default, Deserialize)]
#[serde(default)]
pub struct Snapshot {
    pub spaces: Vec<Space>,
    pub tabs: Vec<Tab>,
    pub panes: Vec<Pane>,
    /// `[orchestration]` settings (Agent tree's Policy panel).
    pub orchestration: Value,
    /// Remote machines, as `RemoteRegistry::public_state` (Machines view).
    pub machines: Value,
    /// Agent actions waiting for the user's allow/deny (Inbox).
    pub policy_pending: Vec<Value>,
}

/// One message from the daemon.
#[derive(Debug, Clone, PartialEq)]
pub enum ServerMsg {
    Reply { id: u64, result: Result<Value, String> },
    Event { name: String, data: Value },
    Output { pane: String, data: String, replay: bool },
    Other,
}

impl ServerMsg {
    pub fn parse(text: &str) -> ServerMsg {
        let Ok(v) = serde_json::from_str::<Value>(text) else { return ServerMsg::Other };
        let s = |k: &str| v[k].as_str().unwrap_or("").to_string();
        match v["t"].as_str().unwrap_or("") {
            "res" => {
                let result = match v.get("error").filter(|e| !e.is_null()) {
                    Some(e) => Err(e["message"].as_str().unwrap_or("error").to_string()),
                    None => Ok(v.get("result").cloned().unwrap_or(Value::Null)),
                };
                ServerMsg::Reply { id: v["id"].as_u64().unwrap_or(0), result }
            }
            "ev" => ServerMsg::Event { name: s("name"), data: v.get("data").cloned().unwrap_or(Value::Null) },
            "out" => ServerMsg::Output { pane: s("pane"), data: s("data"), replay: false },
            "replay" => ServerMsg::Output { pane: s("pane"), data: s("data"), replay: true },
            _ => ServerMsg::Other,
        }
    }
}
