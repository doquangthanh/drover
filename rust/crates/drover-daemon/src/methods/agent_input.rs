//! RPC methods for driving an agent's UI: prompt (and wait), named keys, waiting for output text.
//! Port of `methods_agent_input.py`, plus the scrolling read of a full-screen agent (`alt_screen_history_reader.py`).

use std::collections::HashSet;
use std::sync::Arc;
use std::time::{Duration, Instant};

use serde_json::{Value, json};

use drover_core::alt_screen_pages::{MAX_PAGES, NOTCHES_PER_PAGE, PAGE_SETTLE_SECS, WHEEL_DOWN, WHEEL_UP, fixed_chrome, merge_pages, wheel};
use drover_core::pane_session::PaneSession;
use drover_core::status_tracker::now_secs;
use drover_core::terminal_keys::encode_keys;

use super::pane_param;
use super::panes::{gate_agent_input, mark_busy, wait_for_state};
use crate::ctx::Ctx;
use crate::method;
use crate::rpc::{E_BAD_PARAMS, E_BLOCKED, E_GENERAL, E_STALLED, E_TIMEOUT, MethodSpec, RpcError, RpcResult, need_str, opt_f64, opt_i64, truthy};

const STALL_SECONDS: f64 = 5.0; // a prompt that shows no sign of work this long after Enter has "stalled"
const PASTE_ENTER_DELAY: Duration = Duration::from_millis(50); // let the app take the paste before Enter
const OUTPUT_POLL: Duration = Duration::from_millis(250);
const BLOCKED_MESSAGE: &str = "agent_blocked: the agent is waiting on a question or permission prompt; nothing was sent. \
Read it with `dr read`; the user answers permission prompts";

pub fn methods() -> Vec<MethodSpec> {
    vec![
        method!("pane.prompt", "Submit a prompt to an agent; refuses one on a permission prompt", "pane, text, wait?, states?, timeout?, caller?", pane_prompt),
        method!("pane.keys", "Press named keys in a pane (esc, enter, up, ctrl+c, shift+tab...)", "pane, keys: [names], caller?", pane_keys),
        method!("pane.wait_output", "Block until text (or a regex) shows in a pane's recent output", "pane, pattern, regex?, lines?, timeout?", pane_wait_output),
    ]
}

fn caller(p: &Value) -> Option<&str> {
    p.get("caller").and_then(Value::as_str).filter(|c| !c.is_empty())
}

/// Type the prompt (bracketed paste when the app asked for it), then Enter. Returns the moment just before Enter.
pub async fn submit(pane: &PaneSession, text: &str) -> Result<f64, RpcError> {
    if pane.state.lock().unwrap().screen.modes().bracketed_paste {
        pane.write(&format!("\x1b[200~{}\x1b[201~", text.replace("\x1b[201~", ""))); // the text cannot end the paste
    } else {
        pane.write(text);
    }
    tokio::time::sleep(PASTE_ENTER_DELAY).await;
    if pane.state_name() == "blocked" {
        // A dialog opened while we typed: never let our Enter answer it.
        return Err(RpcError::new(E_BLOCKED, BLOCKED_MESSAGE.replace("nothing was sent", "the text was typed but not submitted")));
    }
    let enter_at = now_secs();
    pane.write("\r");
    Ok(enter_at)
}

/// Wait until the agent looks busy (or asks something) after `since`; error if it never does.
async fn await_activity(pane: &PaneSession, since: f64, timeout: f64) -> Result<(), RpcError> {
    let deadline = Instant::now() + Duration::from_secs_f64(STALL_SECONDS.min(timeout).max(0.0));
    while Instant::now() < deadline {
        let (busy, state) = {
            let st = pane.state.lock().unwrap();
            (st.tracker.detected_working_at >= since && st.screen_changed_at >= since, st.tracker.state.clone())
        };
        if busy || state == "blocked" || state == "exited" {
            return Ok(());
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    if timeout <= STALL_SECONDS {
        return Err(RpcError::new(E_TIMEOUT, format!("timed out after {timeout:.0}s; state is {}", pane.state_name())));
    }
    Err(RpcError::new(E_STALLED, "agent_prompt_stalled: prompt sent but the agent did not start working; \
`dr read` it before retrying so the prompt is not sent twice"))
}

async fn pane_prompt(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let (pane_id, pane) = {
        let m = ctx.manager.lock().unwrap();
        let id = pane_param(&m, &p, "pane")?;
        let pane = m.get(&id)?;
        (id, pane)
    };
    let text = need_str(&p, "text")?;
    let t0 = Instant::now();
    let timeout = opt_f64(&p, "timeout", 600.0)?;
    let started_at = {
        let lock = ctx.input_lock(&pane_id);
        let _guard = lock.lock().await; // a second prompt must not land between this one's text and its Enter
        let state = pane.state_name();
        if state == "blocked" {
            return Err(RpcError::new(E_BLOCKED, BLOCKED_MESSAGE));
        }
        if state == "exited" || state == "stopped" {
            return Err(RpcError::new(E_GENERAL, format!("agent is {state}")));
        }
        let at = submit(&pane, &text).await?;
        mark_busy(&ctx.manager.lock().unwrap(), &pane);
        at
    };
    if let Some(c) = caller(&p) {
        ctx.manager.lock().unwrap().messages.add("send", Some(c), Some(&pane_id), &text);
    }
    if !truthy(&p, "wait") {
        return Ok(json!({"pane": pane_id, "state": pane.state_name()}));
    }
    await_activity(&pane, started_at, timeout).await?;
    let mut wanted: HashSet<String> = p.get("states").and_then(Value::as_array).filter(|a| !a.is_empty())
        .map(|a| a.iter().filter_map(|s| s.as_str().map(String::from)).collect())
        .unwrap_or_else(|| ["done", "idle", "blocked"].map(String::from).into());
    wanted.insert("exited".into());
    let remaining = timeout - t0.elapsed().as_secs_f64();
    // mark_busy forced "working", so idle/done now really means this turn settled.
    let state = wait_for_state(&ctx, &pane, wanted, remaining, true).await?;
    Ok(json!({"pane": pane_id, "state": state}))
}

async fn pane_keys(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let mut m = ctx.manager.lock().unwrap();
    let pane_id = pane_param(&m, &p, "pane")?;
    let pane = m.get(&pane_id)?;
    let names: Vec<String> = match p.get("keys").and_then(Value::as_array) {
        Some(a) if a.iter().all(Value::is_string) => a.iter().filter_map(|n| n.as_str().map(String::from)).collect(),
        _ => return Err(RpcError::new(E_BAD_PARAMS, "keys must be a list of key names")),
    };
    let data = encode_keys(&names).map_err(|e| RpcError::new(E_BAD_PARAMS, e))?;
    let label = names.join(" ");
    gate_agent_input(&ctx, &mut m, &pane_id, &pane, &data, &format!("[keys] {label}"), caller(&p))?;
    pane.write(&data);
    if let Some(c) = caller(&p) {
        m.messages.add("keys", Some(c), Some(&pane_id), &label);
    }
    Ok(json!({"pane": pane_id, "keys": names}))
}

async fn pane_wait_output(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let (pane_id, pane) = {
        let m = ctx.manager.lock().unwrap();
        let id = pane_param(&m, &p, "pane")?;
        let pane = m.get(&id)?;
        (id, pane)
    };
    let pattern = need_str(&p, "pattern")?;
    let re = if truthy(&p, "regex") {
        Some(regex::Regex::new(&pattern).map_err(|e| RpcError::new(E_BAD_PARAMS, format!("bad regex: {e}")))?)
    } else {
        None
    };
    let matches = |line: &str| re.as_ref().map_or_else(|| line.contains(&pattern), |r| r.is_match(line));
    let lines = match opt_i64(&p, "lines", 0)? { 0 => 80, n => n.max(1) as usize };
    let timeout = opt_f64(&p, "timeout", 600.0)?;
    if let Some(c) = caller(&p) {
        ctx.manager.lock().unwrap().messages.add("wait", Some(c), Some(&pane_id), &format!("output '{pattern}'"));
    }
    let deadline = Instant::now() + Duration::from_secs_f64(timeout.max(0.0));
    loop {
        let (recent, last_output) = {
            let st = pane.state.lock().unwrap();
            let all = st.screen.all_lines();
            (all[all.len().saturating_sub(lines)..].to_vec(), st.last_output_at)
        };
        if let Some(hit) = recent.iter().rev().find(|l| matches(l)) {
            return Ok(json!({"pane": pane_id, "matched_line": hit, "text": recent.join("\n")}));
        }
        if !ctx.manager.lock().unwrap().panes.contains_key(&pane_id) {
            return Err(RpcError::new(E_GENERAL, "pane was closed before the output appeared"));
        }
        if !pane.alive() && now_secs() - last_output > 1.0 {
            // Exited, and its last output did not match.
            return Err(RpcError::new(E_GENERAL, format!("pane exited before the output appeared (state {})", pane.state_name())));
        }
        if Instant::now() >= deadline {
            return Err(RpcError::new(E_TIMEOUT, format!("timed out after {timeout:.0}s waiting for '{pattern}'")));
        }
        tokio::time::sleep(OUTPUT_POLL).await;
    }
}

async fn scroll(pane: &PaneSession, button: u32, notches: usize) -> Vec<String> {
    let (cols, rows) = { let st = pane.state.lock().unwrap(); (st.cols as usize, st.rows as usize) };
    pane.write(&wheel(button, cols, rows, notches));
    tokio::time::sleep(Duration::from_secs_f64(PAGE_SETTLE_SECS)).await;
    pane.state.lock().unwrap().screen.visible_lines()
}

/// Scroll a full-screen agent up until `wanted` lines are collected or the top stops moving, then back down.
/// Header/footer rows that stay put while scrolling are kept once (footer at the end).
pub async fn read_scrolled_history(pane: &PaneSession, wanted: usize) -> Vec<String> {
    let first = pane.state.lock().unwrap().screen.visible_lines();
    let mut previous = first.clone();
    let (mut top, mut bottom, mut measured) = (0, 0, false);
    let mut body: Vec<String> = vec![];
    let mut up = 0;
    for _ in 0..MAX_PAGES {
        let page = scroll(pane, WHEEL_UP, NOTCHES_PER_PAGE).await;
        up += NOTCHES_PER_PAGE;
        if page == previous {
            break; // reached the top of the transcript
        }
        if !measured {
            (top, bottom) = fixed_chrome(&first, &page);
            body = first[top..first.len() - bottom].to_vec();
            measured = true;
        }
        body = merge_pages(&page[top..page.len() - bottom], &body);
        previous = page;
        if body.len() + bottom >= wanted {
            break;
        }
    }
    if up > 0 {
        scroll(pane, WHEEL_DOWN, up + NOTCHES_PER_PAGE).await;
    }
    let mut lines = if measured { [body, first[first.len() - bottom..].to_vec()].concat() } else { first };
    while lines.last().is_some_and(String::is_empty) {
        lines.pop();
    }
    lines[lines.len().saturating_sub(wanted)..].to_vec()
}

/// `pane.read` for a full-screen agent with more lines than its screen: scroll its own history.
pub async fn read_full_screen_agent(ctx: &Ctx, pane: &PaneSession, lines: usize) -> Option<String> {
    let eligible = {
        let st = pane.state.lock().unwrap();
        lines > st.rows as usize && st.screen.modes().scrollable_transcript() && matches!(st.tracker.state.as_str(), "idle" | "done")
    };
    if !eligible {
        return None;
    }
    let lock = ctx.read_lock(&pane.id());
    let _guard = lock.lock().await; // two readers scrolling the same viewport would interleave pages
    pane.state.lock().unwrap().detection_paused_until = f64::MAX; // our scroll redraws are not the agent working
    let text = read_scrolled_history(pane, lines).await.join("\n");
    // Keep detection paused until the activity window has forgotten our redraws (no working -> done flash).
    pane.state.lock().unwrap().detection_paused_until = now_secs() + drover_core::status_tracker::ACTIVITY_WINDOW + 0.5;
    Some(text)
}
