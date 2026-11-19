//! pane.wait_children: `dr wait --children all|any`, a parent waiting on the helpers it started (Herdr-style).
//! Port of `methods_wait_children.py`.

use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde_json::{Value, json};

use drover_core::status_tracker::now_secs;

use crate::ctx::Ctx;
use crate::method;
use crate::parent_notes::WaitGuard;
use crate::rpc::{E_BAD_PARAMS, E_TIMEOUT, MethodSpec, RpcError, RpcResult, opt_f64};

/// A helper started this recently counts as working: its task may not have reached it yet.
const BOOT_GRACE: f64 = 5.0;
const NEWS_STATES: [&str; 3] = ["done", "blocked", "exited"];

pub fn methods() -> Vec<MethodSpec> {
    vec![method!("pane.wait_children", "Block until the caller's helpers stop working (all) or one has news (any)",
        "caller, mode?: all|any, timeout?", pane_wait_children)]
}

struct Kid {
    id: String,
    name: String,
    state: String,
    created_at: f64,
}

fn kids(ctx: &Ctx, caller: &str) -> Vec<Kid> {
    let m = ctx.manager.lock().unwrap();
    m.children_of(caller).iter().filter_map(|id| m.panes.get(id)).map(|p| {
        let meta = p.meta.lock().unwrap();
        Kid { id: meta.id.clone(), name: meta.name.clone(), state: p.state_name(), created_at: meta.created_at }
    }).collect()
}

fn busy(k: &Kid) -> bool {
    k.state == "working" || (k.state == "idle" && now_secs() - k.created_at < BOOT_GRACE)
}

fn reply(ctx: &Ctx, caller: &str, reason: &str, news: Option<(&str, &str)>) -> Value {
    let all = kids(ctx, caller);
    let reported: Vec<String> = match news {
        Some((pane, _)) => vec![pane.to_string()],
        None => all.iter().map(|k| k.id.clone()).collect(),
    };
    ctx.manager.lock().unwrap().notes.drop_children(caller, &reported);
    let children: Vec<Value> = all.iter().map(|k| json!({"pane": k.id, "name": k.name, "state": k.state})).collect();
    match news {
        Some((pane, state)) => json!({"reason": reason, "pane": pane, "state": state, "children": children}),
        None => json!({"reason": reason, "children": children}),
    }
}

async fn pane_wait_children(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let caller = p.get("caller").and_then(Value::as_str).unwrap_or("").to_string();
    if !ctx.manager.lock().unwrap().panes.contains_key(&caller) {
        return Err(RpcError::new(E_BAD_PARAMS, "wait --children only works inside a drover pane (DR_PANE_ID)"));
    }
    let mode = p.get("mode").and_then(Value::as_str).unwrap_or("all").to_string();
    if mode != "all" && mode != "any" {
        return Err(RpcError::new(E_BAD_PARAMS, "mode must be 'all' or 'any'"));
    }
    let timeout = opt_f64(&p, "timeout", 600.0)?;
    let now_kids = kids(&ctx, &caller);
    if now_kids.is_empty() {
        return Ok(reply(&ctx, &caller, "no_children", None));
    }
    if !now_kids.iter().any(busy) {
        return Ok(reply(&ctx, &caller, if mode == "all" { "all" } else { "none_working" }, None));
    }
    let news: Arc<Mutex<Vec<(String, String)>>> = Arc::default();
    let changed = Arc::new(tokio::sync::Notify::new());
    let (news_l, changed_l, parent) = (news.clone(), changed.clone(), caller.clone());
    let sub = ctx.hub.subscribe(move |name, data| {
        if name != "status" || data["pane"]["parent"].as_str() != Some(parent.as_str()) {
            return;
        }
        let new = data["new"].as_str().unwrap_or("");
        let finished = data["old"] == "working" && new == "idle";
        if NEWS_STATES.contains(&new) || finished {
            let id = data["pane"]["id"].as_str().unwrap_or("").to_string();
            news_l.lock().unwrap().push((id, if finished { "done".into() } else { new.to_string() }));
        }
        changed_l.notify_one();
    });
    ctx.manager.lock().unwrap().messages.add("wait", Some(&caller), None, &format!("children:{mode}"));
    let guard = WaitGuard::new(&ctx.manager, Some(&caller));
    let deadline = Instant::now() + Duration::from_secs_f64(timeout.max(0.0));
    let result = loop {
        let first = news.lock().unwrap().first().cloned();
        if mode == "any" && let Some((pane, state)) = first {
            break Ok((Some((pane, state)), "child"));
        }
        if mode == "all" && !kids(&ctx, &caller).iter().any(busy) {
            break Ok((None, "all"));
        }
        let left = deadline.saturating_duration_since(Instant::now());
        if left.is_zero() {
            let states: Vec<String> = kids(&ctx, &caller).iter().map(|k| format!("{} {}", k.name, k.state)).collect();
            break Err(RpcError::new(E_TIMEOUT, format!("timed out after {timeout:.0}s; helpers: {}", states.join(", "))));
        }
        // Also wakes to re-check the boot grace, which no status event announces.
        let _ = tokio::time::timeout(left.min(Duration::from_millis(500)), changed.notified()).await;
    };
    ctx.hub.unsubscribe(sub);
    drop(guard);
    let (news, reason) = result?;
    Ok(reply(&ctx, &caller, reason, news.as_ref().map(|(p, s)| (p.as_str(), s.as_str()))))
}
