//! Binary split tree for pane layout inside a tab. Port of `drover/core/split_layout_tree.py`.
//!
//! JSON shapes (same as the Python daemon and `frontend/src/core/protocol-types.ts`):
//!   `{"pane": "%3"}`
//!   `{"split": "row" | "col", "ratio": 0.5, "a": <node>, "b": <node>}`
//! "row" = side by side (split right), "col" = stacked (split down).

use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Dir {
    Row,
    Col,
}

fn half() -> f64 {
    0.5
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Node {
    Pane {
        pane: String,
    },
    Split {
        split: Dir,
        #[serde(default = "half")]
        ratio: f64,
        a: Box<Node>,
        b: Box<Node>,
    },
}

pub fn leaf(pane_id: &str) -> Node {
    Node::Pane { pane: pane_id.to_string() }
}

fn split(dir: Dir, ratio: f64, a: Node, b: Node) -> Node {
    Node::Split { split: dir, ratio, a: Box::new(a), b: Box::new(b) }
}

pub fn pane_ids(node: Option<&Node>) -> Vec<String> {
    let mut out = Vec::new();
    fn walk(n: &Node, out: &mut Vec<String>) {
        match n {
            Node::Pane { pane } => out.push(pane.clone()),
            Node::Split { a, b, .. } => {
                walk(a, out);
                walk(b, out);
            }
        }
    }
    if let Some(n) = node {
        walk(n, &mut out);
    }
    out
}

/// Split `target` leaf (or the last leaf if target is missing) and place `new_pane` after it.
pub fn insert(node: Option<&Node>, target: Option<&str>, new_pane: &str, dir: Dir) -> Node {
    let Some(node) = node else { return leaf(new_pane) };
    let ids = pane_ids(Some(node));
    let target = match target {
        Some(t) if ids.iter().any(|i| i == t) => t.to_string(),
        _ => ids.last().cloned().unwrap_or_default(),
    };
    split_at(node, &target, new_pane, dir)
}

fn split_at(node: &Node, target: &str, new_pane: &str, dir: Dir) -> Node {
    match node {
        Node::Pane { pane } if pane == target => split(dir, 0.5, node.clone(), leaf(new_pane)),
        Node::Pane { .. } => node.clone(),
        Node::Split { split: d, ratio, a, b } => {
            split(*d, *ratio, split_at(a, target, new_pane, dir), split_at(b, target, new_pane, dir))
        }
    }
}

/// Remove a leaf; its sibling takes the parent's place.
pub fn remove(node: Option<&Node>, pane_id: &str) -> Option<Node> {
    match node? {
        Node::Pane { pane } if pane == pane_id => None,
        n @ Node::Pane { .. } => Some(n.clone()),
        Node::Split { split: d, ratio, a, b } => match (remove(Some(a), pane_id), remove(Some(b), pane_id)) {
            (None, b) => b,
            (a, None) => a,
            (Some(a), Some(b)) => Some(split(*d, *ratio, a, b)),
        },
    }
}

/// Update the ratio of the split at `path` ("" = root, then "a"/"b" steps), clamped to 0.1..=0.9.
pub fn set_ratio(node: Option<&Node>, path: &str, new_ratio: f64) -> Option<Node> {
    let node = node?;
    let Node::Split { split: d, ratio, a, b } = node else { return Some(node.clone()) };
    let Some(step) = path.chars().next() else {
        return Some(split(*d, new_ratio.clamp(0.1, 0.9), (**a).clone(), (**b).clone()));
    };
    let rest = &path[1..];
    let (a, b) = if step == 'a' {
        (set_ratio(Some(a), rest, new_ratio).unwrap_or((**a).clone()), (**b).clone())
    } else {
        ((**a).clone(), set_ratio(Some(b), rest, new_ratio).unwrap_or((**b).clone()))
    };
    Some(split(*d, *ratio, a, b))
}

/// A JSON value from a client is a well-formed layout node.
pub fn is_valid(value: &Value) -> bool {
    serde_json::from_value::<Node>(value.clone()).is_ok()
}

/// Exchange two panes' places in one tree (either may be absent: then it is a plain replace).
pub fn swap_leaves(node: Option<&Node>, x: &str, y: &str) -> Option<Node> {
    Some(match node? {
        Node::Pane { pane } if pane == x => leaf(y),
        Node::Pane { pane } if pane == y => leaf(x),
        n @ Node::Pane { .. } => n.clone(),
        Node::Split { split: d, ratio, a, b } => split(
            *d,
            *ratio,
            swap_leaves(Some(a), x, y).unwrap_or((**a).clone()),
            swap_leaves(Some(b), x, y).unwrap_or((**b).clone()),
        ),
    })
}

/// Steps ("a"/"b") from the root to a pane's leaf, or None when it is not in the tree.
pub fn path_to(node: Option<&Node>, pane_id: &str) -> Option<String> {
    fn walk(n: &Node, id: &str, path: String) -> Option<String> {
        match n {
            Node::Pane { pane } => (pane == id).then_some(path),
            Node::Split { a, b, .. } => walk(a, id, format!("{path}a")).or_else(|| walk(b, id, format!("{path}b"))),
        }
    }
    walk(node?, pane_id, String::new())
}

/// Give a pane (its side of the nearest enclosing split) `share` of that split's space.
pub fn set_share(node: Option<&Node>, pane_id: &str, share: f64) -> Result<Option<Node>, String> {
    let path = path_to(node, pane_id).filter(|p| !p.is_empty());
    let Some(path) = path else {
        return Err(format!("{pane_id} is alone in its tab; nothing to resize against"));
    };
    let (parent, last) = path.split_at(path.len() - 1);
    Ok(set_ratio(node, parent, if last == "a" { share } else { 1.0 - share }))
}

#[cfg(test)]
#[path = "layout_tree_tests.rs"]
mod tests;
