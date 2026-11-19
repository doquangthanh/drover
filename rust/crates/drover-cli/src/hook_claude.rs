//! `dr hook claude`: Claude Code hook (SubagentStart / SubagentStop) -> sub-agent lane events on the Flow board.
//! Port of `cli_hook_claude.py`. Claude runs it with the payload on stdin and the pane's env (DR_PANE_ID). It must
//! never slow down or break Claude: it prints nothing, times out fast, swallows every error and exits 0.

use std::io::Read;
use std::time::Duration;

use serde_json::{Value, json};

const MAX_TEXT: usize = 200;

/// Map a hook payload to `agent.subagent` params; None for events and payloads we don't use.
pub fn payload_to_params(payload: &Value, pane: &str) -> Option<Value> {
    let event = match payload.get("hook_event_name").and_then(Value::as_str)? {
        "SubagentStart" => "start",
        "SubagentStop" => "stop",
        _ => return None,
    };
    let agent_id = payload.get("agent_id").and_then(Value::as_str).filter(|a| !a.is_empty())?;
    if pane.is_empty() {
        return None;
    }
    let raw = if event == "stop" { payload.get("last_assistant_message").and_then(Value::as_str).unwrap_or("") } else { "" };
    let text = raw.split_whitespace().collect::<Vec<_>>().join(" ");
    let text = if text.chars().count() <= MAX_TEXT { text } else { text.chars().take(MAX_TEXT).collect::<String>() + "…" };
    let name = payload.get("agent_type").and_then(Value::as_str).filter(|n| !n.is_empty()).unwrap_or("agent");
    Some(json!({"pane": pane, "event": event, "id": agent_id, "name": name, "text": text}))
}

pub fn run() -> i32 {
    let mut stdin = String::new();
    let _ = std::io::stdin().read_to_string(&mut stdin);
    let payload: Value = serde_json::from_str(if stdin.trim().is_empty() { "{}" } else { &stdin }).unwrap_or(Value::Null);
    if let Some(Value::Object(params)) = payload_to_params(&payload, &std::env::var("DR_PANE_ID").unwrap_or_default()) {
        // like `dc.call(..., timeout=2, autostart=False)`; every error is swallowed
        let _ = crate::daemon_rpc::call("agent.subagent", params, Duration::from_secs(2));
    }
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn maps_start_and_stop_and_ignores_the_rest() {
        let start = json!({"hook_event_name": "SubagentStart", "agent_id": "a1", "agent_type": "Explore"});
        assert_eq!(payload_to_params(&start, "%3").unwrap()["name"], "Explore");
        let stop = json!({"hook_event_name": "SubagentStop", "agent_id": "a1", "last_assistant_message": "done\n  here"});
        assert_eq!(payload_to_params(&stop, "%3").unwrap()["text"], "done here");
        assert!(payload_to_params(&json!({"hook_event_name": "PreToolUse", "agent_id": "a"}), "%3").is_none());
        assert!(payload_to_params(&start, "").is_none());
    }
}
