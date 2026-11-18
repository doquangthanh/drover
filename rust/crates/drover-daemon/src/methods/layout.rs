//! RPC methods that shape the layout from scripts: new tabs, split, move, swap, zoom and share of a split.
//! Port of `methods_layout.py`. Every method returns the ids it created or touched.

use std::sync::Arc;

use serde_json::{Value, json};

use drover_core::layout_tree::{self as layout, Dir};

use super::{caller_pane, pane_param};
use crate::ctx::Ctx;
use crate::manager::Manager;
use crate::manager_panes::NewPane;
use crate::method;
use crate::rpc::{MethodSpec, RpcError, RpcResult, bad, flag, need_str, not_found, opt_str, truthy};

pub fn methods() -> Vec<MethodSpec> {
    vec![
        method!("tab.create", "New tab in a space with a shell or command", "space, command?, name?", tab_create),
        method!("pane.split", "Split a pane and start a shell or command beside it", "pane, direction?: right|down, command?, name?, cwd?", pane_split),
        method!("pane.move", "Move a pane into another tab (or a new tab)", "pane, tab? | new_tab?, direction?", pane_move),
        method!("pane.swap", "Swap two panes' places (same or different tabs)", "pane, target", pane_swap),
        method!("pane.zoom", "Zoom a pane to fill its tab (zoomed=false restores)", "pane, zoomed?", pane_zoom),
        method!("pane.share", "Set how much of its split a pane takes (0.1-0.9)", "pane, share", pane_share),
    ]
}

fn direction(p: &Value) -> Result<Dir, RpcError> {
    let value = match opt_str(p, "direction") { v if v.is_empty() => "right".to_string(), v => v };
    match value.as_str() {
        "right" | "row" => Ok(Dir::Row),
        "down" | "col" => Ok(Dir::Col),
        _ => Err(bad("direction must be right or down")),
    }
}

fn tab_json(m: &Manager, id: &str) -> Value {
    m.tabs.get(id).map(|t| serde_json::to_value(t).unwrap_or_default()).unwrap_or(Value::Null)
}

async fn tab_create(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let mut m = ctx.manager.lock().unwrap();
    let space_id = need_str(&p, "space")?;
    let cwd = m.spaces.get(&space_id).ok_or_else(|| not_found(&space_id))?.cwd.clone();
    let name = match opt_str(&p, "name") { n if n.is_empty() => "tab".to_string(), n => n.chars().take(60).collect() };
    let tab_id = m.create_tab(&space_id, &name);
    let parent = caller_pane(&m, &p);
    let req = NewPane { command: opt_str(&p, "command"), cwd, name: opt_str(&p, "name"), tab_id: Some(tab_id.clone()), parent, ..Default::default() };
    let pane = match m.create_pane(req) {
        Ok(p) => p,
        Err(e) => {
            m.tabs.shift_remove(&tab_id); // don't leave an empty tab behind
            return Err(e.policy_rpc());
        }
    };
    if !truthy(&p, "name") {
        let pane_name = pane.meta.lock().unwrap().name.clone();
        if let Some(t) = m.tabs.get_mut(&tab_id) {
            t.name = pane_name;
        }
        m.changed(); // create_pane already published the tab under its placeholder name
    }
    Ok(json!({"tab": tab_json(&m, &tab_id), "pane": pane.to_json()}))
}

async fn pane_split(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let mut m = ctx.manager.lock().unwrap();
    let target = m.get(&pane_param(&m, &p, "pane")?)?;
    let meta = target.meta.lock().unwrap().clone();
    let cwd = match opt_str(&p, "cwd") { c if c.is_empty() => meta.cwd.clone(), c => c };
    let req = NewPane { command: opt_str(&p, "command"), cwd, name: opt_str(&p, "name"), tab_id: Some(meta.tab_id.clone()),
        split_from: Some(meta.id.clone()), direction: Some(direction(&p)?), parent: caller_pane(&m, &p), ..Default::default() };
    let pane = m.create_pane(req).map_err(|e| e.policy_rpc())?;
    Ok(json!({"pane": pane.to_json()}))
}

async fn pane_move(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let mut m = ctx.manager.lock().unwrap();
    let pane = m.get(&pane_param(&m, &p, "pane")?)?;
    let dir = direction(&p)?; // validate everything before the pane leaves its tab
    let (space_id, name, previous_tab, id) = { let x = pane.meta.lock().unwrap(); (x.space_id.clone(), x.name.clone(), x.tab_id.clone(), x.id.clone()) };
    let target = if truthy(&p, "new_tab") {
        m.create_tab(&space_id, &name)
    } else {
        let t = need_str(&p, "tab")?;
        if !m.tabs.contains_key(&t) {
            return Err(not_found(&t));
        }
        if t == previous_tab {
            return Err(bad("pane is already in that tab"));
        }
        t
    };
    m.detach_from_tab(&pane);
    let tab = m.tabs.get_mut(&target).expect("target tab");
    tab.layout = Some(layout::insert(tab.layout.as_ref(), tab.focused.as_deref(), &id, dir));
    tab.focused = Some(id.clone());
    let new_space = tab.space_id.clone();
    {
        let mut x = pane.meta.lock().unwrap();
        x.tab_id = target.clone();
        x.space_id = new_space;
    }
    m.changed();
    Ok(json!({"pane": pane.to_json(), "tab": tab_json(&m, &target), "previous_tab": previous_tab}))
}

async fn pane_swap(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let mut m = ctx.manager.lock().unwrap();
    let a = m.get(&pane_param(&m, &p, "pane")?)?;
    let b = m.get(&pane_param(&m, &p, "target")?)?;
    if Arc::ptr_eq(&a, &b) {
        return Err(bad("cannot swap a pane with itself"));
    }
    let (a_id, a_tab, a_space) = { let x = a.meta.lock().unwrap(); (x.id.clone(), x.tab_id.clone(), x.space_id.clone()) };
    let (b_id, b_tab, b_space) = { let x = b.meta.lock().unwrap(); (x.id.clone(), x.tab_id.clone(), x.space_id.clone()) };
    for t in [&a_tab, &b_tab] {
        if !m.tabs.contains_key(t) {
            return Err(not_found(t));
        }
    }
    let tabs = if a_tab == b_tab { vec![a_tab.clone()] } else { vec![a_tab.clone(), b_tab.clone()] };
    for t in &tabs {
        let tab = m.tabs.get_mut(t).expect("checked");
        tab.layout = layout::swap_leaves(tab.layout.as_ref(), &a_id, &b_id);
        if a_tab != b_tab && (tab.focused.as_deref() == Some(&a_id) || tab.focused.as_deref() == Some(&b_id)) {
            tab.focused = Some(if tab.focused.as_deref() == Some(&a_id) { b_id.clone() } else { a_id.clone() });
        }
    }
    {
        let mut x = a.meta.lock().unwrap();
        x.tab_id = b_tab.clone();
        x.space_id = b_space;
    }
    {
        let mut x = b.meta.lock().unwrap();
        x.tab_id = a_tab;
        x.space_id = a_space;
    }
    m.changed();
    Ok(json!({"panes": [a.to_json(), b.to_json()]}))
}

async fn pane_zoom(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let mut m = ctx.manager.lock().unwrap();
    let pane = m.get(&pane_param(&m, &p, "pane")?)?;
    let (id, tab_id) = { let x = pane.meta.lock().unwrap(); (x.id.clone(), x.tab_id.clone()) };
    let tab = m.tabs.get_mut(&tab_id).ok_or_else(|| not_found(&tab_id))?;
    tab.focused = Some(id);
    tab.zoomed = flag(&p, "zoomed", true);
    m.changed();
    Ok(json!({"tab": tab_json(&m, &tab_id)}))
}

async fn pane_share(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let mut m = ctx.manager.lock().unwrap();
    let pane = m.get(&pane_param(&m, &p, "pane")?)?;
    let share = p.get("share").filter(|v| v.is_number()).and_then(Value::as_f64).filter(|s| (0.1..=0.9).contains(s))
        .ok_or_else(|| bad("share must be a number from 0.1 to 0.9"))?;
    let (id, tab_id) = { let x = pane.meta.lock().unwrap(); (x.id.clone(), x.tab_id.clone()) };
    let tab = m.tabs.get_mut(&tab_id).ok_or_else(|| not_found(&tab_id))?;
    tab.layout = layout::set_share(tab.layout.as_ref(), &id, share).map_err(bad)?;
    m.changed();
    Ok(json!({"tab": tab_json(&m, &tab_id)}))
}
