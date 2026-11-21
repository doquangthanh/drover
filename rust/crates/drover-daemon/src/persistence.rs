//! Save the workspace to session.json and bring it back after a restart. Port of `session_persistence.py`.
//! The file format is the Python one, so either daemon resumes the other's session.

use std::path::Path;

use serde_json::{Value, json};

use drover_core::layout_tree::{self as layout, Dir};
use drover_core::status_tracker::now_secs;
use drover_core::workspace_models::{Space, Tab, bump_id_counter};

use crate::manager::Manager;
use crate::manager_panes::{NewPane, SpawnError};
use crate::state_store::StateStore;

pub fn serialize(m: &Manager) -> Value {
    let mut panes: Vec<Value> = m.panes.values().map(|p| {
        let meta = p.meta.lock().unwrap();
        json!({"id": meta.id, "name": meta.name, "kind": meta.kind, "command": meta.command, "cwd": meta.cwd,
               "space_id": meta.space_id, "tab_id": meta.tab_id, "parent": meta.parent, "resume": meta.resume})
    }).collect();
    panes.extend(m.stopped.iter().cloned());
    json!({"version": crate::state_store::SESSION_VERSION, "saved_at": now_secs(),
           "spaces": m.spaces.values().map(|s| serde_json::to_value(s).unwrap_or_default()).collect::<Vec<_>>(),
           "tabs": m.tabs.values().map(|t| serde_json::to_value(t).unwrap_or_default()).collect::<Vec<_>>(),
           "panes": panes})
}

/// Recreate spaces and tabs; previous panes become `stopped` entries awaiting resume.
pub fn load_previous(m: &mut Manager, store: &StateStore) {
    let data = store.load();
    if data.is_empty() {
        return;
    }
    for raw in data.get("spaces").and_then(Value::as_array).into_iter().flatten() {
        let mut raw = raw.clone();
        if raw.get("custom_name").is_none() {
            // Older files: a name that is not the folder's own name was set by hand.
            let cwd = raw["cwd"].as_str().unwrap_or("");
            let own = Path::new(cwd).file_name().and_then(|n| n.to_str()).filter(|n| !n.is_empty()).unwrap_or(cwd);
            raw["custom_name"] = json!(raw["name"].as_str() != Some(own));
        }
        if let Ok(space) = serde_json::from_value::<Space>(raw) {
            m.spaces.insert(space.id.clone(), space);
        }
    }
    for raw in data.get("tabs").and_then(Value::as_array).into_iter().flatten() {
        let layout_ok = raw.get("layout").is_some_and(layout::is_valid);
        let slim = json!({"id": raw["id"], "space_id": raw["space_id"], "name": raw["name"],
                          "layout": raw["layout"], "focused": raw["focused"]});
        if let (true, Ok(tab)) = (layout_ok, serde_json::from_value::<Tab>(slim)) {
            m.tabs.insert(tab.id.clone(), tab);
        }
    }
    m.stopped = data.get("panes").and_then(Value::as_array).into_iter().flatten()
        .filter(|p| p["tab_id"].as_str().is_some_and(|t| m.tabs.contains_key(t)))
        .cloned().collect();
    let known: Vec<String> = m.stopped.iter().filter_map(|p| p["id"].as_str().map(String::from)).collect();
    let tab_ids: Vec<String> = m.tabs.keys().cloned().collect();
    for tid in tab_ids {
        let tab = &mut m.tabs[&tid];
        for pane_id in layout::pane_ids(tab.layout.as_ref()) {
            if !known.contains(&pane_id) {
                tab.layout = layout::remove(tab.layout.as_ref(), &pane_id);
            }
        }
        if tab.layout.is_none() {
            m.tabs.shift_remove(&tid);
        }
    }
    let ids: Vec<String> = m.spaces.keys().chain(m.tabs.keys()).cloned().chain(known).collect();
    bump_id_counter(ids.iter().map(String::as_str));
}

pub fn resume(m: &mut Manager, pane_ids: &[String], use_resume_command: bool) -> Result<Vec<String>, SpawnError> {
    let mut started = vec![];
    let todo: Vec<Value> = m.stopped.iter().filter(|p| p["id"].as_str().is_some_and(|i| pane_ids.iter().any(|x| x == i))).cloned().collect();
    // (folder, resume command) already running: live panes, then each pane resumed below.
    let mut taken: Vec<(String, String)> = m.panes.values().map(|p| {
        let meta = p.meta.lock().unwrap();
        (meta.cwd.clone(), meta.resume.clone())
    }).filter(|(_, r)| !r.is_empty()).collect();
    for old in todo {
        let s = |k: &str| old[k].as_str().unwrap_or("").to_string();
        let mut command = if use_resume_command { claim_resume(&mut taken, &s("cwd"), s("resume")) } else { String::new() };
        if command.is_empty() {
            command = s("command");
        }
        if s("kind") == "shell" {
            command.clear();
        }
        let pane = m.create_pane(NewPane { command, cwd: s("cwd"), name: s("name"), tab_id: Some(s("tab_id")),
            split_from: Some(s("id")), direction: Some(Dir::Row), ..Default::default() })?;
        let new_id = pane.id();
        if let Some(tab) = m.tabs.get_mut(&s("tab_id")) {
            tab.layout = layout::remove(tab.layout.as_ref(), &s("id"));
            tab.focused = Some(new_id.clone());
        }
        m.stopped.retain(|p| p["id"] != old["id"]);
        started.push(new_id);
    }
    m.changed();
    Ok(started)
}

/// Herdr's duplicate rule: two panes resuming one conversation (`codex resume --last` twice, one id twice) would
/// type into the same transcript. The first claim of a (folder, command) keeps it; later ones get "" (start fresh).
fn claim_resume(taken: &mut Vec<(String, String)>, cwd: &str, command: String) -> String {
    if command.is_empty() {
        return command;
    }
    let key = (cwd.to_string(), command);
    if taken.contains(&key) {
        return String::new();
    }
    let command = key.1.clone();
    taken.push(key);
    command
}

pub fn discard(m: &mut Manager, pane_ids: Option<&[String]>) {
    let drop: Vec<Value> = m.stopped.iter()
        .filter(|p| pane_ids.is_none_or(|ids| p["id"].as_str().is_some_and(|i| ids.iter().any(|x| x == i))))
        .cloned().collect();
    for old in drop {
        let tab_id = old["tab_id"].as_str().unwrap_or("").to_string();
        if let Some(tab) = m.tabs.get_mut(&tab_id) {
            tab.layout = layout::remove(tab.layout.as_ref(), old["id"].as_str().unwrap_or(""));
            if tab.layout.is_none() {
                m.tabs.shift_remove(&tab_id);
            }
        }
        m.stopped.retain(|p| p["id"] != old["id"]);
    }
    m.changed();
}

#[cfg(test)]
mod tests {
    use super::claim_resume;

    #[test]
    fn a_conversation_is_resumed_once() {
        let mut taken = vec![("/w/a".to_string(), "claude --resume X".to_string())]; // a live pane runs X
        assert_eq!(claim_resume(&mut taken, "/w/a", "claude --resume X".into()), "");
        assert_eq!(claim_resume(&mut taken, "/w/b", "codex resume --last".into()), "codex resume --last");
        assert_eq!(claim_resume(&mut taken, "/w/b", "codex resume --last".into()), "");
        assert_eq!(claim_resume(&mut taken, "/w/c", "codex resume --last".into()), "codex resume --last");
        assert_eq!(claim_resume(&mut taken, "/w/c", String::new()), "");
    }
}
