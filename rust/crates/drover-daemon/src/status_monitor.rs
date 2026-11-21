//! Background loop: run detection rules on panes, publish state changes. Port of `status_monitor.py`.

use std::sync::Arc;
use std::time::{Duration, UNIX_EPOCH};

use serde_json::json;

use drover_core::detection_rules::load_rule_sets;
use drover_core::foreground_probe::running_agent;
use drover_core::pane_session::PaneSession;
use drover_core::status_detector::evaluate;
use drover_core::status_tracker::now_secs;

use crate::claude_session::{has_transcript, resume_command, running_session_id};
use crate::codex_session;
use crate::ctx::Ctx;
use crate::manager::Manager;

const TICK: Duration = Duration::from_millis(250);
const AGENT_SESSION_EVERY: f64 = 5.0; // /clear, /new or /resume inside the agent switches the conversation

pub async fn run(ctx: Arc<Ctx>) {
    let mut last_config_check = 0.0;
    let mut rules_stamp: Option<Vec<(String, std::time::SystemTime)>> = None;
    loop {
        tick(&ctx, &mut last_config_check, &mut rules_stamp);
        tokio::time::sleep(TICK).await;
    }
}

fn tick(ctx: &Arc<Ctx>, last_config_check: &mut f64, rules_stamp: &mut Option<Vec<(String, std::time::SystemTime)>>) {
    let now = now_secs();
    let mut m = ctx.manager.lock().unwrap();
    if now - *last_config_check > 2.0 {
        *last_config_check = now;
        ctx.settings.lock().unwrap().reload_if_changed();
        reload_rules(ctx, &mut m, rules_stamp);
        m.follow_space_folders();
    }
    let panes: Vec<Arc<PaneSession>> = m.panes.values().cloned().collect();
    for pane in panes {
        probe_foreground(&mut m, &pane, now);
        probe_agent_session(&m, &pane, now);
        check_pane(&mut m, &pane, now);
        // An OSC 7501 `summary=` changes the sidebar line without a state change.
        if std::mem::take(&mut pane.state.lock().unwrap().summary_changed) {
            m.hub.emit("pane", pane.to_json());
        }
    }
    deliver_parent_notes(ctx, &mut m, now);
}

/// Type queued helper notes into parents that can take them now (see `parent_notes.rs`).
fn deliver_parent_notes(ctx: &Arc<Ctx>, m: &mut Manager, now: f64) {
    for (parent_id, text) in m.notes.take_ready(&m.panes, now) {
        let Some(pane) = m.panes.get(&parent_id).cloned() else { continue };
        m.notes.sending.insert(parent_id.clone());
        let ctx = ctx.clone();
        tokio::spawn(async move {
            let lock = ctx.input_lock(&parent_id);
            let typed = {
                let _held = lock.lock().await;
                crate::methods::agent_input::submit(&pane, &text).await
            };
            if let Err(e) = typed {
                // Blocked meanwhile, or the pane closed: the note is dropped; the Flow board has the event.
                crate::log::info(&format!("parent note to {parent_id} not typed: {}", e.message));
            }
            ctx.manager.lock().unwrap().notes.sending.remove(&parent_id);
        });
    }
}

fn reload_rules(ctx: &Ctx, m: &mut Manager, stamp: &mut Option<Vec<(String, std::time::SystemTime)>>) {
    let dir = crate::paths::user_rules_dir();
    let mut now: Vec<(String, std::time::SystemTime)> = std::fs::read_dir(&dir).into_iter().flatten().flatten()
        .filter(|e| e.path().extension().is_some_and(|x| x == "toml"))
        .filter_map(|e| Some((e.file_name().to_string_lossy().into_owned(), e.metadata().ok()?.modified().ok()?)))
        .collect();
    now.sort();
    if stamp.as_ref() == Some(&now) {
        return;
    }
    *stamp = Some(now);
    let (sets, errors) = load_rule_sets(Some(&dir));
    m.rule_sets = sets;
    *ctx.rule_errors.lock().unwrap() = errors;
}

/// Herdr-style: a shell pane is that agent while the agent runs in it (same path on every platform).
fn probe_foreground(m: &mut Manager, pane: &Arc<PaneSession>, now: f64) {
    const EVERY: f64 = 2.0; // and at once when the foreground group changes (Linux; Windows has none)
    if !pane.alive() || !pane.state.lock().unwrap().shell_launched {
        return;
    }
    let group = pane.foreground_pgid();
    {
        let mut st = pane.state.lock().unwrap();
        if st.fg_pgid == group && now - st.fg_checked_at < EVERY {
            return;
        }
        st.fg_pgid = group;
        st.fg_checked_at = now;
    }
    let kinds: Vec<&str> = m.rule_sets.iter().map(|r| r.id.as_str()).collect();
    let found = running_agent(pane.pid(), group, &kinds);
    pane.state.lock().unwrap().fg_agent = found.as_ref().map(|(pid, _)| *pid);
    m.set_pane_kind(pane, found.as_ref().map_or("shell", |(_, kind)| kind.as_str()));
}

/// Resume a Claude or Codex pane into its own conversation, not the folder's (or machine's) newest.
fn probe_agent_session(m: &Manager, pane: &Arc<PaneSession>, now: f64) {
    let kind = pane.meta.lock().unwrap().kind.clone();
    if !matches!(kind.as_str(), "claude" | "codex") || !pane.alive() {
        return;
    }
    {
        let mut st = pane.state.lock().unwrap();
        if now - st.claude_checked_at < AGENT_SESSION_EVERY {
            return;
        }
        st.claude_checked_at = now;
    }
    let found = if kind == "claude" { claude_resume(pane) } else { codex_resume(m, pane) };
    let Some(cmd) = found else { return };
    if cmd == pane.meta.lock().unwrap().resume {
        return;
    }
    pane.meta.lock().unwrap().resume = cmd;
    m.save.notify_one(); // save it, so a daemon or computer restart resumes this conversation
}

fn claude_resume(pane: &PaneSession) -> Option<String> {
    // Typed in a shell, claude is the agent the foreground probe found; started by drover, the pane's own process.
    let typed = pane.state.lock().unwrap().fg_agent;
    let pids = [typed, pane.pid()].into_iter().flatten().map(|p| p as i32);
    let sid = running_session_id(pids)?;
    has_transcript(&sid).then(|| resume_command(&sid))
}

fn codex_resume(m: &Manager, pane: &Arc<PaneSession>) -> Option<String> {
    let (cwd, created_at) = {
        let meta = pane.meta.lock().unwrap();
        (meta.cwd.clone(), meta.created_at)
    };
    let cwd = Manager::pane_follow_cwd(pane).unwrap_or(cwd);
    // Codex's files only tell conversations apart by folder: with two Codex panes in one folder, guessing could swap
    // them, so both keep the default resume (and `persistence::resume` starts the second one fresh).
    let shared = m.panes.values()
        .filter(|p| !Arc::ptr_eq(p, pane) && p.alive() && p.meta.lock().unwrap().kind == "codex")
        .any(|p| Manager::pane_follow_cwd(p).is_some_and(|c| codex_session::same_folder(&c, &cwd)));
    if shared {
        return None;
    }
    let since = UNIX_EPOCH + Duration::from_secs_f64(created_at.max(0.0));
    codex_session::newest_session_in(&cwd, since).map(|id| codex_session::resume_command(&id))
}

fn check_pane(m: &mut Manager, pane: &Arc<PaneSession>, now: f64) {
    let (kind, created_at, parent, id) = {
        let meta = pane.meta.lock().unwrap();
        (meta.kind.clone(), meta.created_at, meta.parent.clone(), meta.id.clone())
    };
    let mut st = pane.state.lock().unwrap();
    let recent = now - st.last_output_at < 3.0;
    // New input holds "working" for a few seconds; keep evaluating until the idle candidate has debounced.
    let settling = now < st.tracker.hold_until + 1.5;
    if now < st.detection_paused_until {
        return; // `dr read` is scrolling the agent: its redraws are ours, not the agent working
    }
    if !(st.dirty || recent || settling || st.tracker.has_pending_candidate()) {
        return;
    }
    st.dirty = false;
    let title = st.screen.title();
    let (detected, _) = evaluate(m.rule_set(&kind), &title, &st.screen.visible_lines());
    let old = st.tracker.state.clone();
    // Shells go idle after every command; only agents get a "done". Start-up output is not finished work either.
    let worked_after_boot = st.tracker.since - created_at > 4.0;
    let allow_done = kind != "shell" && worked_after_boot;
    let focused = st.focused;
    let last_output = st.last_output_at;
    let Some(new) = st.tracker.observe(detected.as_deref(), last_output, focused, now, allow_done) else { return };
    if (new == "blocked" || new == "done") && !focused {
        st.unread = true;
    }
    drop(st);
    // A focused agent finishing its turn goes working -> idle (no "done" badge), but it did finish: log it.
    let finished = allow_done && old == "working" && new == "idle";
    m.messages.add_state(&id, parent.as_deref(), if finished { "done" } else { &new }, "");
    m.report_to_parent(pane, if finished { "done" } else { &new }, "");
    let data = pane.to_json();
    m.hub.emit("pane", data.clone());
    m.hub.emit("status", json!({"pane": data, "old": old, "new": new}));
    if !focused {
        let name = pane.meta.lock().unwrap().name.clone();
        crate::notify::notify_state(&m.settings.lock().unwrap(), &name, &kind, &new, &title);
    }
}
