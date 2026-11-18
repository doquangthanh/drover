//! RPC for Claude Code sub-agents (Task/Agent tool) reported by `dr hook claude`: one virtual lane per sub-agent.
//! Port of `methods_subagents.py`.

use std::sync::Arc;

use serde_json::Value;

use crate::ctx::Ctx;
use crate::method;
use crate::rpc::{E_BAD_PARAMS, E_NOT_FOUND, MethodSpec, RpcError, RpcResult, need_str, opt_str};

pub fn methods() -> Vec<MethodSpec> {
    vec![method!("agent.subagent", "A Claude Code sub-agent started or stopped inside a pane", "pane, event, id, name?, text?", agent_subagent)]
}

async fn agent_subagent(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let (pane_id, event, agent_id) = (need_str(&p, "pane")?, need_str(&p, "event")?, need_str(&p, "id")?);
    let mut m = ctx.manager.lock().unwrap();
    if !m.panes.contains_key(&pane_id) {
        return Err(RpcError::new(E_NOT_FOUND, format!("no pane {pane_id}")));
    }
    if (event != "start" && event != "stop") || agent_id.contains('/') {
        return Err(RpcError::new(E_BAD_PARAMS, "event must be start or stop; id has no '/'"));
    }
    // Sub-agent id on the Flow board: `<pane>/<agent>`; MessagesLog::for_tree keeps it with its pane's tree.
    let sub = format!("{pane_id}/{agent_id}");
    let message = if event == "start" {
        let name = match opt_str(&p, "name") { n if n.is_empty() => "agent".to_string(), n => n };
        m.messages.add("sub-start", Some(&pane_id), Some(&sub), &name)
    } else {
        m.messages.add("sub-done", Some(&sub), Some(&pane_id), &opt_str(&p, "text"))
    };
    // Sub-agents don't change any pane's state, so tell the UI to refetch the tree's messages.
    m.hub.emit("messages", message);
    Ok(Value::Null)
}
