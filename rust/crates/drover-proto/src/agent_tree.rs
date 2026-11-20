//! Agent tree logic shared by native views (port of `frontend/src/views/views-logic.ts` and
//! `agent-flow-logic.ts`): who started whom, filtering, the selected tree, and `messages.list` entries.

use std::collections::{HashMap, HashSet};

use serde::Deserialize;

use crate::wire::Pane;

/// One row of the tree. `guides[i]`: the ancestor at depth i still has siblings below, so its line keeps going.
#[derive(Debug, Clone, PartialEq)]
pub struct TreeRow {
    pub id: String,
    pub guides: Vec<bool>,
    pub last: bool,
}

/// Agents only: shells are not part of the tree.
pub fn agents(panes: &[Pane]) -> Vec<&Pane> {
    panes.iter().filter(|p| p.kind != "shell").collect()
}

/// Depth-first flattening. A helper whose parent was closed becomes a root.
pub fn tree_rows(panes: &[&Pane]) -> Vec<TreeRow> {
    let ids: HashSet<&str> = panes.iter().map(|p| p.id.as_str()).collect();
    let is_root = |p: &Pane| p.parent.as_deref().is_none_or(|parent| !ids.contains(parent));
    let mut out = vec![];
    let mut seen = HashSet::new();
    fn walk<'a>(panes: &[&'a Pane], parent: Option<&str>, guides: Vec<bool>, is_root: &dyn Fn(&Pane) -> bool,
                seen: &mut HashSet<&'a str>, out: &mut Vec<TreeRow>) {
        let kids: Vec<&Pane> = panes.iter().copied().filter(|p| !seen.contains(p.id.as_str()) && match parent {
            None => is_root(p),
            Some(id) => p.parent.as_deref() == Some(id),
        }).collect();
        for (i, p) in kids.iter().enumerate() {
            let last = i + 1 == kids.len();
            seen.insert(p.id.as_str());
            out.push(TreeRow { id: p.id.clone(), guides: guides.clone(), last });
            let mut next = guides.clone();
            next.push(!last);
            walk(panes, Some(&p.id), next, is_root, seen, out);
        }
    }
    walk(panes, None, vec![], &is_root, &mut seen, &mut out);
    out
}

/// Rows whose name or title matches `query`, plus their ancestors so the tree shape stays readable.
pub fn filter_rows(rows: &[TreeRow], panes: &[&Pane], query: &str) -> Vec<TreeRow> {
    let q = query.trim().to_lowercase();
    if q.is_empty() {
        return rows.to_vec();
    }
    let by_id: HashMap<&str, &Pane> = panes.iter().map(|p| (p.id.as_str(), *p)).collect();
    let mut keep: HashSet<&str> = HashSet::new();
    for row in rows {
        let Some(p) = by_id.get(row.id.as_str()) else { continue };
        if !format!("{} {}", p.name, p.title).to_lowercase().contains(&q) {
            continue;
        }
        let mut cur = Some(*p);
        while let Some(p) = cur.filter(|p| !keep.contains(p.id.as_str())) {
            keep.insert(p.id.as_str());
            cur = p.parent.as_deref().and_then(|id| by_id.get(id).copied());
        }
    }
    rows.iter().filter(|r| keep.contains(r.id.as_str())).cloned().collect()
}

/// Top-most ancestor that still exists.
pub fn root_of(id: &str, panes: &[&Pane]) -> String {
    let by_id: HashMap<&str, &Pane> = panes.iter().map(|p| (p.id.as_str(), *p)).collect();
    let mut seen = HashSet::new();
    let mut cur = id;
    while let Some(parent) = by_id.get(cur).and_then(|p| p.parent.as_deref()).filter(|p| by_id.contains_key(p)) {
        if !seen.insert(cur) {
            break;
        }
        cur = parent;
    }
    cur.to_string()
}

/// The pane and all its helpers, depth first (same order as the tree).
pub fn subtree_ids(root: &str, panes: &[&Pane]) -> Vec<String> {
    let mut out: Vec<String> = vec![];
    let mut stack = vec![root.to_string()];
    while let Some(id) = stack.pop() {
        if out.contains(&id) {
            continue;
        }
        let kids: Vec<String> = panes.iter().filter(|p| p.parent.as_deref() == Some(id.as_str())).map(|p| p.id.clone()).collect();
        out.push(id);
        stack.extend(kids.into_iter().rev());
    }
    out
}

/// One `messages.list` entry: what an agent did to another (`dr run`, `dr send`, `dr wait`...).
#[derive(Debug, Clone, Default, Deserialize, PartialEq)]
#[serde(default)]
pub struct AgentMessage {
    pub at: f64,
    pub source: Option<String>,
    pub target: Option<String>,
    pub kind: String,
    pub text: String,
}

/// Sentence verb of a message kind (Messages tab).
pub fn message_verb(kind: &str) -> &str {
    match kind {
        "spawn" => "started",
        "wait" => "is waiting for",
        "send" => "→",
        "keys" => "pressed keys in",
        "read" => "read",
        "done" => "finished for",
        "blocked" => "needs an answer — asked",
        "denied" => "tried to answer for",
        "exited" => "exited, reported to",
        "sub-start" => "delegated to sub-agent",
        "sub-done" => "returned to",
        other => other,
    }
}

/// Short verb of a message kind (Flow arrows).
pub fn flow_verb(kind: &str) -> &str {
    match kind {
        "spawn" => "started",
        "wait" => "waits for",
        "send" => "sends",
        "keys" => "keys",
        "read" => "read",
        "done" => "finished",
        "blocked" => "asks",
        "denied" => "tried to answer",
        "exited" => "exited",
        "sub-start" => "delegates",
        "sub-done" => "returned",
        other => other,
    }
}

/// Messages touching any of `ids` (an empty source or target is "you", id "").
pub fn touches(m: &AgentMessage, ids: &HashSet<String>) -> bool {
    ids.contains(m.source.as_deref().unwrap_or("")) || ids.contains(m.target.as_deref().unwrap_or(""))
}

/// Count of panes per state.
pub fn state_count(panes: &[&Pane], state: &str) -> usize {
    panes.iter().filter(|p| p.state == state).count()
}
