//! Owns spaces, tabs and panes on this machine. All mutations go through here. Port of `session_manager.py`
//! (pane creation and exit live in `manager_panes.rs`).

use std::collections::HashMap;
use std::path::Path;
use std::sync::{Arc, Mutex, Weak};

use indexmap::IndexMap;
use serde_json::{Value, json};
use tokio::sync::Notify;

use drover_core::detection_rules::AgentRuleSet;
use drover_core::foreground_probe::follow_cwd;
use drover_core::layout_tree as layout;
use drover_core::pane_session::PaneSession;
use drover_core::workspace_models::{Space, Tab, new_id};

use crate::event_hub::EventHub;
use crate::messages_log::MessagesLog;
use crate::rpc::{RpcError, not_found};
use crate::settings::Settings;

pub struct Manager {
    pub settings: Arc<Mutex<Settings>>,
    pub hub: Arc<EventHub>,
    pub rule_sets: Vec<AgentRuleSet>,
    pub spaces: IndexMap<String, Space>,
    pub tabs: IndexMap<String, Tab>,
    pub panes: IndexMap<String, Arc<PaneSession>>,
    /// Panes from a previous run, offered for resume (raw session.json entries).
    pub stopped: Vec<Value>,
    /// Space id -> {branch, dirty, ahead}, refreshed by the git watcher.
    pub git: HashMap<String, Value>,
    pub messages: MessagesLog,
    /// Typed into a parent agent when a helper finishes, asks or exits.
    pub notes: crate::parent_notes::ParentNotes,
    /// Structure changed: the persistence task saves session.json shortly after.
    pub save: Arc<Notify>,
    pub me: Weak<Mutex<Manager>>,
}

pub type SharedManager = Arc<Mutex<Manager>>;

/// Canonical form of a folder, for comparing spaces (`os.path.normcase(Path(cwd).resolve())`).
pub fn resolve_dir(cwd: &str) -> String {
    let p = std::fs::canonicalize(cwd).map(|p| p.to_string_lossy().into_owned()).unwrap_or_else(|_| cwd.to_string());
    #[cfg(windows)]
    let p = p.trim_start_matches(r"\\?\").to_string();
    p
}

fn same_dir(a: &str, b: &str) -> bool {
    if cfg!(windows) { a.eq_ignore_ascii_case(b) } else { a == b }
}

impl Manager {
    pub fn new(settings: Arc<Mutex<Settings>>, hub: Arc<EventHub>, rule_sets: Vec<AgentRuleSet>, save: Arc<Notify>) -> SharedManager {
        Arc::new_cyclic(|me| {
            Mutex::new(Manager {
                settings, hub, rule_sets, save,
                spaces: IndexMap::new(), tabs: IndexMap::new(), panes: IndexMap::new(),
                stopped: vec![], git: HashMap::new(), messages: MessagesLog::default(), notes: Default::default(), me: me.clone(),
            })
        })
    }

    pub fn rule_set(&self, kind: &str) -> Option<&AgentRuleSet> {
        self.rule_sets.iter().find(|r| r.id == kind)
    }

    // -- spaces & tabs ------------------------------------------------------------------------
    pub fn ensure_space(&mut self, cwd: &str) -> String {
        let norm = resolve_dir(cwd);
        if let Some(s) = self.spaces.values().find(|s| same_dir(&resolve_dir(&s.cwd), &norm)) {
            return s.id.clone();
        }
        let space = Space::for_folder(&norm, (self.spaces.len() % 8) as i64);
        let id = space.id.clone();
        self.spaces.insert(id.clone(), space);
        id
    }

    /// Always a new space, even when another space already has this folder (`space.create` with new).
    pub fn add_space(&mut self, cwd: &str) -> String {
        let mut space = Space::for_folder(&resolve_dir(cwd), (self.spaces.len() % 8) as i64);
        let base = space.name.clone();
        let mut n = 2;
        while self.spaces.values().any(|s| s.name == space.name) {
            space.name = format!("{base}-{n}");
            n += 1;
        }
        let id = space.id.clone();
        self.spaces.insert(id.clone(), space);
        id
    }

    pub fn create_tab(&mut self, space_id: &str, name: &str) -> String {
        let tab = Tab { id: new_id("t"), space_id: space_id.into(), name: name.into(), layout: None, focused: None,
            zoomed: false, extra: Default::default() };
        let id = tab.id.clone();
        self.tabs.insert(id.clone(), tab);
        id
    }

    pub fn remove_space(&mut self, space_id: &str) {
        let tab_ids: Vec<String> = self.tabs.values().filter(|t| t.space_id == space_id).map(|t| t.id.clone()).collect();
        for tab_id in tab_ids {
            let ids = layout::pane_ids(self.tabs[&tab_id].layout.as_ref());
            for pane_id in ids {
                if self.panes.contains_key(&pane_id) {
                    let _ = self.close_pane(&pane_id, false);
                }
            }
            self.tabs.shift_remove(&tab_id);
        }
        // Panes from a previous run in this space are not live: just forget them.
        self.stopped.retain(|s| s["space_id"].as_str() != Some(space_id));
        self.spaces.shift_remove(space_id);
        self.changed();
    }

    // -- panes --------------------------------------------------------------------------------
    pub fn get(&self, pane_id: &str) -> Result<Arc<PaneSession>, RpcError> {
        self.panes.get(pane_id).cloned().ok_or_else(|| not_found(format!("no pane {pane_id}")))
    }

    pub fn depth_of(&self, mut pane_id: Option<String>) -> Option<i64> {
        let (mut depth, mut seen) = (None, std::collections::HashSet::new());
        while let Some(id) = pane_id.filter(|i| self.panes.contains_key(i) && seen.insert(i.clone())) {
            depth = Some(depth.unwrap_or(0) + 1);
            pane_id = self.panes[&id].meta.lock().unwrap().parent.clone();
        }
        depth
    }

    pub fn report_to_parent(&mut self, pane: &PaneSession, state: &str, detail: &str) {
        let (id, name, parent) = { let m = pane.meta.lock().unwrap(); (m.id.clone(), m.name.clone(), m.parent.clone()) };
        let on = self.settings.lock().unwrap().bool("orchestration.notes", true);
        if let Some(parent) = parent.filter(|p| self.panes.contains_key(p))
            && on && crate::parent_notes::NOTE_STATES.contains(&state)
        {
            self.notes.add(&parent, &id, &name, state, detail);
        }
    }

    pub fn children_of(&self, pane_id: &str) -> Vec<String> {
        self.panes.values().filter(|p| p.meta.lock().unwrap().parent.as_deref() == Some(pane_id)).map(|p| p.id()).collect()
    }

    pub fn default_name(&self, kind: &str) -> String {
        let taken: Vec<String> = self.panes.values().map(|p| p.meta.lock().unwrap().name.clone()).collect();
        (1..1000).map(|n| if n == 1 { kind.to_string() } else { format!("{kind}-{n}") })
            .find(|c| !taken.contains(c)).unwrap_or_else(|| kind.to_string())
    }

    /// A shell pane started or left an agent: switch kind, resume command and an auto-given name.
    pub fn set_pane_kind(&mut self, pane: &Arc<PaneSession>, kind: &str) {
        let resume = self.rule_set(kind).map(|r| r.resume.clone()).unwrap_or_default();
        let default_name = self.default_name(kind);
        let renamed = {
            let mut m = pane.meta.lock().unwrap();
            if m.kind == kind {
                return;
            }
            let auto = regex::Regex::new(&format!("^{}(-\\d+)?$", regex::escape(&m.kind))).unwrap();
            let renamed = auto.is_match(&m.name).then(|| (m.tab_id.clone(), std::mem::replace(&mut m.name, default_name.clone())));
            m.kind = kind.to_string();
            m.resume = resume;
            renamed
        };
        // A tab is named after its first pane ("shell"); follow the auto-rename unless the tab was renamed by hand.
        if let Some((tab_id, old_name)) = renamed
            && let Some(tab) = self.tabs.get_mut(&tab_id)
            && tab.name == old_name
        {
            tab.name = default_name;
            self.hub.emit("state", Value::Null); // tabs travel in the full state
        }
        self.hub.emit("pane", pane.to_json());
        self.save.notify_one();
    }

    /// Folder the pane is in now: the program in front (Linux: foreground group; Windows: the agent the shell
    /// started), else the shell.
    pub fn pane_follow_cwd(pane: &PaneSession) -> Option<String> {
        if !pane.alive() {
            return None;
        }
        let front = pane.foreground_pgid().or_else(|| pane.state.lock().unwrap().fg_agent.map(|p| p as i32));
        follow_cwd(front, pane.pid().map(|p| p as i32))
    }

    /// Herdr-style: a space is named after the folder its first pane is in, unless renamed by hand.
    pub fn follow_space_folders(&mut self) {
        let mut changed = false;
        let space_ids: Vec<String> = self.spaces.keys().cloned().collect();
        for sid in space_ids {
            if self.spaces[&sid].custom_name {
                continue;
            }
            let first = self.tabs.values().find(|t| t.space_id == sid && t.layout.is_some())
                .and_then(|t| layout::pane_ids(t.layout.as_ref()).into_iter().next());
            let Some(cwd) = first.and_then(|id| self.panes.get(&id).cloned()).and_then(|p| Self::pane_follow_cwd(&p)) else { continue };
            let space = &mut self.spaces[&sid];
            if cwd == space.cwd {
                continue;
            }
            space.name = Path::new(&cwd).file_name().and_then(|n| n.to_str()).filter(|n| !n.is_empty()).unwrap_or(&cwd).to_string();
            space.cwd = cwd;
            changed = true;
        }
        if changed {
            self.changed();
        }
    }

    pub fn close_pane(&mut self, pane_id: &str, notify: bool) -> Result<(), RpcError> {
        let pane = self.panes.shift_remove(pane_id).ok_or_else(|| not_found(pane_id))?;
        pane.kill(false);
        self.detach_from_tab(&pane);
        if notify {
            self.changed();
        }
        Ok(())
    }

    /// Take a pane out of its tab's layout; a tab left empty is removed.
    pub fn detach_from_tab(&mut self, pane: &PaneSession) {
        let (tab_id, id) = { let m = pane.meta.lock().unwrap(); (m.tab_id.clone(), m.id.clone()) };
        let Some(tab) = self.tabs.get_mut(&tab_id) else { return };
        tab.layout = layout::remove(tab.layout.as_ref(), &id);
        if tab.focused.as_deref() == Some(id.as_str()) {
            tab.focused = layout::pane_ids(tab.layout.as_ref()).last().cloned();
            tab.zoomed = false; // the zoom belonged to the pane that left
        }
        if tab.layout.is_none() {
            self.tabs.shift_remove(&tab_id);
        }
    }

    pub fn focus(&mut self, pane_id: &str) -> Result<(), RpcError> {
        let pane = self.get(pane_id)?;
        for p in self.panes.values() {
            p.state.lock().unwrap().focused = p.id() == pane_id;
        }
        {
            let mut st = pane.state.lock().unwrap();
            st.unread = false;
            st.tracker.acknowledge();
        }
        let tab_id = pane.meta.lock().unwrap().tab_id.clone();
        if let Some(tab) = self.tabs.get_mut(&tab_id) {
            tab.focused = Some(pane_id.to_string());
        }
        self.hub.emit("pane", pane.to_json());
        Ok(())
    }

    // -- snapshot -----------------------------------------------------------------------------
    pub fn space_json(&self, s: &Space) -> Value {
        let mut v = serde_json::to_value(s).unwrap_or_default();
        if let (Some(obj), Some(Value::Object(git))) = (v.as_object_mut(), self.git.get(&s.id)) {
            obj.extend(git.clone());
        }
        v
    }

    pub fn snapshot(&self) -> Value {
        json!({
            "spaces": self.spaces.values().map(|s| self.space_json(s)).collect::<Vec<_>>(),
            "tabs": self.tabs.values().map(|t| serde_json::to_value(t).unwrap_or_default()).collect::<Vec<_>>(),
            "panes": self.panes.values().map(|p| p.to_json()).collect::<Vec<_>>(),
            "stopped": self.stopped,
        })
    }

    /// Structure changed: push state to clients and save soon.
    pub fn changed(&self) {
        self.hub.emit("state", Value::Null);
        self.save.notify_one();
    }
}
