//! Spaces (a folder/repo on a machine) and tabs (a layout of panes). Port of `drover/core/workspace_models.py`.

use std::path::Path;
use std::sync::atomic::{AtomicU64, Ordering};

use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

use crate::layout_tree::Node;

static NEXT_ID: AtomicU64 = AtomicU64::new(1);

/// One counter for every id kind ("s1", "t2", "%3"), like the Python daemon.
pub fn new_id(prefix: &str) -> String {
    format!("{prefix}{}", NEXT_ID.fetch_add(1, Ordering::SeqCst))
}

/// After restoring from disk make sure new ids don't collide.
pub fn bump_id_counter<'a>(existing: impl IntoIterator<Item = &'a str>) {
    let max = existing
        .into_iter()
        .map(|id| id.chars().filter(char::is_ascii_digit).collect::<String>().parse::<u64>().unwrap_or(0))
        .max()
        .unwrap_or(0);
    NEXT_ID.store(max + 1, Ordering::SeqCst);
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Space {
    pub id: String,
    pub name: String,
    pub cwd: String,
    #[serde(default)]
    pub color: i64,
    /// Renamed by hand: stop naming it after the folder its first pane is in.
    #[serde(default)]
    pub custom_name: bool,
}

impl Space {
    pub fn for_folder(cwd: &str, color: i64) -> Space {
        let name = Path::new(cwd).file_name().and_then(|n| n.to_str()).filter(|n| !n.is_empty()).unwrap_or(cwd);
        Space { id: new_id("s"), name: name.to_string(), cwd: cwd.to_string(), color, custom_name: false }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Tab {
    pub id: String,
    pub space_id: String,
    pub name: String,
    #[serde(default)]
    pub layout: Option<Node>,
    #[serde(default)]
    pub focused: Option<String>,
    #[serde(default)]
    pub zoomed: bool,
    #[serde(default)]
    pub extra: Map<String, Value>,
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::layout_tree::leaf;

    #[test]
    fn space_is_named_after_its_folder() {
        let s = Space::for_folder("/home/me/repo", 2);
        assert_eq!((s.name.as_str(), s.color, s.custom_name), ("repo", 2, false));
        assert!(s.id.starts_with('s'));
        assert_eq!(Space::for_folder("/", 0).name, "/");
    }

    #[test]
    fn tab_json_has_python_keys() {
        let tab = Tab { id: "t1".into(), space_id: "s1".into(), name: "main".into(), layout: Some(leaf("%3")),
            focused: Some("%3".into()), zoomed: false, extra: Map::new() };
        let v = serde_json::to_value(&tab).unwrap();
        assert_eq!(v, serde_json::json!({"id": "t1", "space_id": "s1", "name": "main", "layout": {"pane": "%3"},
            "focused": "%3", "zoomed": false, "extra": {}}));
        let back: Tab = serde_json::from_value(serde_json::json!({"id": "t1", "space_id": "s1", "name": "x"})).unwrap();
        assert_eq!(back.layout, None);
    }

    #[test]
    fn bump_moves_counter_past_restored_ids() {
        bump_id_counter(["s3", "t41", "%17"]);
        let n: u64 = new_id("%").trim_start_matches('%').parse().unwrap();
        assert!(n >= 42);
    }
}
