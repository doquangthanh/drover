//! Notes a helper's parent gets when the helper finishes, needs an answer or exits (Herdr's parent notes).
//! Port of `parent_notes.py`. Typed only when it is safe: the parent is a live agent (not a shell, which would run
//! the text), not on a permission prompt, not inside a `dr wait` that already carries the news, and the person has
//! no half-typed message in it.

use std::collections::{HashMap, HashSet};
use std::sync::Arc;

use indexmap::IndexMap;

use drover_core::pane_session::PaneSession;

use crate::manager::SharedManager;

pub const NOTE_STATES: [&str; 3] = ["done", "blocked", "exited"];

#[derive(Clone)]
struct Note {
    child: String,
    name: String,
    state: String,
    detail: String,
}

#[derive(Default)]
pub struct ParentNotes {
    queue: IndexMap<String, Vec<Note>>,
    waits: HashMap<String, usize>,
    pub sending: HashSet<String>,
}

impl ParentNotes {
    pub fn add(&mut self, parent: &str, child: &str, name: &str, state: &str, detail: &str) {
        let notes = self.queue.entry(parent.to_string()).or_default();
        notes.retain(|n| n.child != child); // only a helper's latest news counts
        notes.push(Note { child: child.into(), name: name.into(), state: state.into(), detail: detail.into() });
    }

    /// A `dr wait` reply already told the parent about these helpers.
    pub fn drop_children(&mut self, parent: &str, children: &[String]) {
        if let Some(notes) = self.queue.get_mut(parent) {
            notes.retain(|n| !children.contains(&n.child));
            if notes.is_empty() {
                self.queue.shift_remove(parent);
            }
        }
    }

    fn begin_wait(&mut self, parent: &str) {
        *self.waits.entry(parent.to_string()).or_default() += 1;
    }

    fn end_wait(&mut self, parent: &str) {
        if let Some(n) = self.waits.get_mut(parent) {
            *n -= 1;
            if *n == 0 {
                self.waits.remove(parent);
            }
        }
    }

    /// (parent id, text) for every parent that can take its notes now; those notes leave the queue.
    pub fn take_ready(&mut self, panes: &IndexMap<String, Arc<PaneSession>>, now: f64) -> Vec<(String, String)> {
        let mut ready = vec![];
        for parent in self.queue.keys().cloned().collect::<Vec<_>>() {
            let Some(pane) = panes.get(&parent).filter(|p| p.alive()) else {
                self.queue.shift_remove(&parent);
                continue;
            };
            let busy = pane.meta.lock().unwrap().kind == "shell" || pane.state_name() == "blocked"
                || self.waits.contains_key(&parent) || self.sending.contains(&parent)
                || pane.state.lock().unwrap().draft.blocks(now);
            if busy {
                continue;
            }
            let notes = self.queue.shift_remove(&parent).unwrap_or_default();
            ready.push((parent, notes.iter().map(format_note).collect::<Vec<_>>().join(" ")));
        }
        ready
    }
}

fn format_note(n: &Note) -> String {
    let what = match n.state.as_str() {
        "done" => format!("finished; read it with: dr read {}", n.name),
        "blocked" => format!("is waiting for the user to answer a prompt; see it with: dr read {}", n.name),
        _ => format!("exited ({})", if n.detail.is_empty() { "no exit code" } else { &n.detail }),
    };
    format!("<dr from=\"{} {}\" state=\"{}\">{what}</dr>", n.child, n.name, n.state)
}

/// Holds a parent's notes while one of its `dr wait` calls runs (they would only repeat the reply).
pub struct WaitGuard {
    manager: SharedManager,
    parent: Option<String>,
}

impl WaitGuard {
    pub fn new(manager: &SharedManager, parent: Option<&str>) -> WaitGuard {
        let parent = parent.filter(|p| !p.is_empty()).map(String::from);
        if let Some(p) = &parent {
            manager.lock().unwrap().notes.begin_wait(p);
        }
        WaitGuard { manager: manager.clone(), parent }
    }
}

impl Drop for WaitGuard {
    fn drop(&mut self) {
        if let Some(p) = &self.parent {
            self.manager.lock().unwrap().notes.end_wait(p);
        }
    }
}
