//! RPC methods for spaces, tabs, layout, restore and search. Port of `methods_workspace.py`.

use std::collections::HashSet;
use std::sync::Arc;

use serde_json::{Value, json};

use drover_core::layout_tree::{self as layout, Node};

use crate::ctx::Ctx;
use crate::manager::Manager;
use crate::manager_panes::NewPane;
use crate::method;
use crate::persistence;
use crate::rpc::{E_GENERAL, MethodSpec, RpcResult, bad, need_str, not_found, opt_str, truthy};

pub fn methods() -> Vec<MethodSpec> {
    vec![
        method!("state.get", "Full snapshot: spaces, tabs, panes, stopped panes", "", state_get),
        method!("space.create", "Open a folder as a space (starts a shell); new: always a fresh space; from: start in the folder that pane is in now", "cwd?, command?, new?, from?", space_create),
        method!("space.rename", "Rename a space", "space, name", space_rename),
        method!("space.remove", "Close a space and all its panes", "space", space_remove),
        method!("tab.set_layout", "Replace a tab's split tree (from drag-resize)", "tab, layout", tab_set_layout),
        method!("tab.rename", "Rename a tab", "tab, name", tab_rename),
        method!("tab.zoom", "Toggle zoom of the focused pane", "tab, zoomed", tab_zoom),
        method!("tab.close", "Close every pane in a tab", "tab", tab_close),
        method!("session.resume", "Restart panes from the previous session", "panes?, fresh?", session_resume),
        method!("session.discard", "Forget panes from the previous session", "panes?", session_discard),
        method!("search.query", "Find agents, spaces and scrollback text", "q", search_query),
        method!("messages.list", "Agent-to-agent actions for the agent tree", "pane?", messages_list),
    ]
}

fn short(s: &str) -> String {
    s.chars().take(60).collect()
}

fn string_list(v: Option<&Value>) -> Option<Vec<String>> {
    v.and_then(Value::as_array).map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect())
}

async fn state_get(ctx: Arc<Ctx>, _p: Value) -> RpcResult {
    Ok(ctx.manager.lock().unwrap().snapshot())
}

async fn space_create(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let mut m = ctx.manager.lock().unwrap();
    let mut cwd = opt_str(&p, "cwd");
    if cwd.is_empty() && let Some(src) = m.panes.get(&opt_str(&p, "from")).cloned() {
        cwd = Manager::pane_follow_cwd(&src).unwrap_or_else(|| src.meta.lock().unwrap().cwd.clone());
    }
    let req = NewPane { command: opt_str(&p, "command"), cwd, new_space: truthy(&p, "new"), ..Default::default() };
    let pane = m.create_pane(req).map_err(|e| e.rpc(E_GENERAL))?;
    let space_id = pane.meta.lock().unwrap().space_id.clone();
    Ok(json!({"space_id": space_id, "pane": pane.to_json()}))
}

async fn space_rename(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let mut m = ctx.manager.lock().unwrap();
    let id = need_str(&p, "space")?;
    let name = short(&need_str(&p, "name")?);
    let space = m.spaces.get_mut(&id).ok_or_else(|| not_found(&id))?;
    space.name = name;
    space.custom_name = true;
    m.changed();
    Ok(Value::Null)
}

async fn space_remove(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    ctx.manager.lock().unwrap().remove_space(&need_str(&p, "space")?);
    Ok(Value::Null)
}

async fn tab_set_layout(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let mut m = ctx.manager.lock().unwrap();
    let id = need_str(&p, "tab")?;
    let tab = m.tabs.get_mut(&id).ok_or_else(|| not_found(&id))?;
    let new: Option<Node> = p.get("layout").and_then(|v| serde_json::from_value(v.clone()).ok());
    let sorted = |n: Option<&Node>| { let mut v = layout::pane_ids(n); v.sort(); v };
    match new {
        Some(n) if sorted(Some(&n)) == sorted(tab.layout.as_ref()) => tab.layout = Some(n),
        _ => return Err(bad("layout must contain exactly the tab's panes")),
    }
    m.changed();
    Ok(Value::Null)
}

async fn tab_rename(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let mut m = ctx.manager.lock().unwrap();
    let id = need_str(&p, "tab")?;
    let name = short(&need_str(&p, "name")?);
    m.tabs.get_mut(&id).ok_or_else(|| not_found(&id))?.name = name;
    m.changed();
    Ok(Value::Null)
}

async fn tab_zoom(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let mut m = ctx.manager.lock().unwrap();
    let id = need_str(&p, "tab")?;
    m.tabs.get_mut(&id).ok_or_else(|| not_found(&id))?.zoomed = truthy(&p, "zoomed");
    m.changed();
    Ok(Value::Null)
}

async fn tab_close(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let mut m = ctx.manager.lock().unwrap();
    let id = need_str(&p, "tab")?;
    let tab = m.tabs.get(&id).ok_or_else(|| not_found(&id))?;
    for pane_id in layout::pane_ids(tab.layout.as_ref()) {
        if m.panes.contains_key(&pane_id) {
            let _ = m.close_pane(&pane_id, false);
        }
    }
    let stopped: Vec<String> = m.stopped.iter().filter(|s| s["tab_id"].as_str() == Some(id.as_str()))
        .filter_map(|s| s["id"].as_str().map(String::from)).collect();
    persistence::discard(&mut m, Some(&stopped));
    m.tabs.shift_remove(&id);
    m.changed();
    Ok(Value::Null)
}

async fn session_resume(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let mut m = ctx.manager.lock().unwrap();
    // "panes": [] means "none" (the user unticked everything); only a missing key means "all".
    let ids = match p.get("panes") {
        Some(v) => string_list(Some(v)).unwrap_or_default(),
        None => m.stopped.iter().filter_map(|s| s["id"].as_str().map(String::from)).collect(),
    };
    if ids.is_empty() {
        return Ok(json!([]));
    }
    let started = persistence::resume(&mut m, &ids, !truthy(&p, "fresh")).map_err(|e| e.rpc(E_GENERAL))?;
    Ok(json!(started))
}

async fn session_discard(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let ids = string_list(p.get("panes"));
    persistence::discard(&mut ctx.manager.lock().unwrap(), ids.as_deref());
    Ok(Value::Null)
}

async fn search_query(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let q = opt_str(&p, "q").trim().to_lowercase();
    if q.is_empty() {
        return Ok(json!({"agents": [], "spaces": [], "text": []}));
    }
    let m = ctx.manager.lock().unwrap();
    let mut agents = vec![];
    let mut text = vec![];
    for pane in m.panes.values() {
        let (name, kind, cwd, id) = { let x = pane.meta.lock().unwrap(); (x.name.clone(), x.kind.clone(), x.cwd.clone(), x.id.clone()) };
        if name.to_lowercase().contains(&q) || kind.contains(&q) || cwd.to_lowercase().contains(&q) {
            agents.push(pane.to_json());
        }
        if text.len() < 50 {
            let hits = pane.state.lock().unwrap().screen.search(&q, 10.min(50 - text.len()));
            text.extend(hits.into_iter().map(|(line, t)| json!({"pane": id, "name": name, "line": line, "text": t})));
        }
    }
    let spaces: Vec<Value> = m.spaces.values().filter(|s| s.name.to_lowercase().contains(&q) || s.cwd.to_lowercase().contains(&q))
        .map(|s| serde_json::to_value(s).unwrap_or_default()).take(20).collect();
    agents.truncate(20);
    Ok(json!({"agents": agents, "spaces": spaces, "text": text}))
}

async fn messages_list(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let m = ctx.manager.lock().unwrap();
    let root = opt_str(&p, "pane");
    let all: Vec<Value> = if root.is_empty() {
        m.messages.items.iter().cloned().collect()
    } else {
        let mut ids: HashSet<String> = HashSet::from([root.clone()]);
        let mut frontier = vec![root];
        while let Some(next) = frontier.pop() {
            for child in m.children_of(&next) {
                if ids.insert(child.clone()) {
                    frontier.push(child);
                }
            }
        }
        m.messages.for_tree(&ids)
    };
    Ok(json!(all[all.len().saturating_sub(200)..]))
}
