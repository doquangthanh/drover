//! Ported from `tests/test_split_layout_tree.py`, plus JSON shape checks against the Python output.

use serde_json::json;

use super::*;

fn two() -> Node {
    insert(Some(&leaf("%1")), Some("%1"), "%2", Dir::Row)
}

fn to_json(n: &Node) -> Value {
    serde_json::to_value(n).unwrap()
}

#[test]
fn pane_ids_of_empty_tree_is_empty() {
    assert!(pane_ids(None).is_empty());
}

#[test]
fn insert_into_empty_tree_makes_single_leaf() {
    assert_eq!(to_json(&insert(None, None, "%1", Dir::Row)), json!({"pane": "%1"}));
}

#[test]
fn insert_splits_target_side_by_side_by_default() {
    assert_eq!(to_json(&two()), json!({"split": "row", "ratio": 0.5, "a": {"pane": "%1"}, "b": {"pane": "%2"}}));
}

#[test]
fn serialized_key_order_matches_python() {
    assert_eq!(serde_json::to_string(&two()).unwrap(), r#"{"split":"row","ratio":0.5,"a":{"pane":"%1"},"b":{"pane":"%2"}}"#);
}

#[test]
fn insert_direction_col_stacks_panes() {
    let tree = insert(Some(&leaf("%1")), Some("%1"), "%2", Dir::Col);
    assert_eq!(to_json(&tree)["split"], "col");
    assert_eq!(pane_ids(Some(&tree)), ["%1", "%2"]);
}

#[test]
fn insert_with_missing_target_splits_last_leaf() {
    let tree = insert(Some(&two()), Some("%missing"), "%3", Dir::Row);
    assert_eq!(pane_ids(Some(&tree)), ["%1", "%2", "%3"]);
    assert_eq!(to_json(&tree)["b"], json!({"split": "row", "ratio": 0.5, "a": {"pane": "%2"}, "b": {"pane": "%3"}}));
}

#[test]
fn pane_ids_keep_left_to_right_order_after_nested_inserts() {
    let mut tree = two();
    tree = insert(Some(&tree), Some("%2"), "%3", Dir::Col);
    tree = insert(Some(&tree), Some("%1"), "%4", Dir::Row);
    assert_eq!(pane_ids(Some(&tree)), ["%1", "%4", "%2", "%3"]);
}

#[test]
fn insert_does_not_mutate_original_tree() {
    let original = two();
    let snapshot = original.clone();
    insert(Some(&original), Some("%1"), "%3", Dir::Row);
    assert_eq!(original, snapshot);
}

#[test]
fn remove_sibling_takes_parent_place() {
    assert_eq!(remove(Some(&two()), "%1"), Some(leaf("%2")));
    assert_eq!(remove(Some(&two()), "%2"), Some(leaf("%1")));
}

#[test]
fn remove_last_pane_returns_none() {
    assert_eq!(remove(Some(&leaf("%1")), "%1"), None);
    assert_eq!(remove(None, "%1"), None);
}

#[test]
fn remove_unknown_pane_keeps_tree() {
    assert_eq!(remove(Some(&two()), "%9"), Some(two()));
}

#[test]
fn remove_from_nested_tree_collapses_only_emptied_branch() {
    let tree = insert(Some(&two()), Some("%2"), "%3", Dir::Col);
    let tree = remove(Some(&tree), "%3").unwrap();
    assert_eq!(to_json(&tree), json!({"split": "row", "ratio": 0.5, "a": {"pane": "%1"}, "b": {"pane": "%2"}}));
}

#[test]
fn set_ratio_on_root_updates_ratio() {
    assert_eq!(to_json(&set_ratio(Some(&two()), "", 0.3).unwrap())["ratio"], 0.3);
}

#[test]
fn set_ratio_clamps_between_point_one_and_point_nine() {
    assert_eq!(to_json(&set_ratio(Some(&two()), "", 0.01).unwrap())["ratio"], 0.1);
    assert_eq!(to_json(&set_ratio(Some(&two()), "", 5.0).unwrap())["ratio"], 0.9);
}

#[test]
fn set_ratio_follows_path_to_nested_split() {
    let tree = insert(Some(&two()), Some("%2"), "%3", Dir::Col);
    let updated = to_json(&set_ratio(Some(&tree), "b", 0.7).unwrap());
    assert_eq!(updated["b"]["ratio"], 0.7);
    assert_eq!(updated["ratio"], 0.5);
}

#[test]
fn set_ratio_on_leaf_or_empty_is_noop() {
    assert_eq!(set_ratio(Some(&leaf("%1")), "", 0.2), Some(leaf("%1")));
    assert_eq!(set_ratio(None, "", 0.2), None);
}

#[test]
fn is_valid_accepts_leaf_and_split() {
    assert!(is_valid(&to_json(&leaf("%1"))));
    assert!(is_valid(&to_json(&two())));
    assert!(is_valid(&json!({"split": "row", "a": {"pane": "%1"}, "b": {"pane": "%2"}})), "ratio is optional");
}

#[test]
fn is_valid_rejects_malformed_nodes() {
    for bad in [
        Value::Null,
        json!("x"),
        json!([]),
        json!({}),
        json!({"pane": 3}),
        json!({"split": "diag", "a": {"pane": "%1"}, "b": {"pane": "%2"}}),
        json!({"split": "row", "a": {"pane": "%1"}}),
        json!({"split": "row", "a": {"pane": "%1"}, "b": "oops"}),
    ] {
        assert!(!is_valid(&bad), "{bad}");
    }
}

#[test]
fn swap_and_share() {
    let tree = swap_leaves(Some(&two()), "%1", "%2").unwrap();
    assert_eq!(pane_ids(Some(&tree)), ["%2", "%1"]);
    assert_eq!(path_to(Some(&tree), "%1").as_deref(), Some("b"));
    let shared = set_share(Some(&tree), "%1", 0.7).unwrap().unwrap();
    assert!((to_json(&shared)["ratio"].as_f64().unwrap() - 0.3).abs() < 1e-9);
    assert!(set_share(Some(&leaf("%1")), "%1", 0.5).is_err());
}
