use std::collections::HashSet;

use crate::agent_tree::*;
use crate::wire::Pane;

fn pane(id: &str, parent: Option<&str>, kind: &str, name: &str) -> Pane {
    Pane { id: id.into(), parent: parent.map(String::from), kind: kind.into(), name: name.into(), ..Default::default() }
}

fn sample() -> Vec<Pane> {
    vec![
        pane("%1", None, "claude", "lead"),
        pane("%2", Some("%1"), "claude", "reviewer"),
        pane("%3", Some("%2"), "codex", "tester"),
        pane("%4", Some("%1"), "claude", "writer"),
        pane("%5", Some("%9"), "claude", "orphan"), // parent closed: becomes a root
        pane("%6", None, "shell", "zsh"),
    ]
}

#[test]
fn tree_rows_are_depth_first_with_guides_and_orphans_as_roots() {
    let all = sample();
    let a = agents(&all);
    assert_eq!(a.len(), 5, "shells are left out");
    let rows = tree_rows(&a);
    let ids: Vec<&str> = rows.iter().map(|r| r.id.as_str()).collect();
    assert_eq!(ids, ["%1", "%2", "%3", "%4", "%5"]);
    assert_eq!(rows[2].guides, vec![true, true], "%1 has a root below (%5), %2 a sibling below (%4)");
    assert!(rows[3].last && !rows[1].last);
}

#[test]
fn filter_keeps_matches_and_their_ancestors() {
    let all = sample();
    let a = agents(&all);
    let rows = tree_rows(&a);
    let ids: Vec<String> = filter_rows(&rows, &a, "TEST").into_iter().map(|r| r.id).collect();
    assert_eq!(ids, ["%1", "%2", "%3"]);
    assert_eq!(filter_rows(&rows, &a, "  ").len(), rows.len());
}

#[test]
fn root_and_subtree() {
    let all = sample();
    let a = agents(&all);
    assert_eq!(root_of("%3", &a), "%1");
    assert_eq!(root_of("%5", &a), "%5");
    assert_eq!(subtree_ids("%1", &a), ["%1", "%2", "%3", "%4"]);
}

#[test]
fn messages_parse_and_touch() {
    let m: Vec<AgentMessage> = serde_json::from_value(serde_json::json!([
        {"at": 1.0, "source": "%1", "target": "%2", "kind": "spawn", "text": "review"},
        {"at": 2.0, "source": null, "target": "%4", "kind": "send"}
    ])).unwrap();
    let ids: HashSet<String> = ["%2".to_string()].into();
    assert!(touches(&m[0], &ids) && !touches(&m[1], &ids));
    let you: HashSet<String> = [String::new()].into();
    assert!(touches(&m[1], &you), "no source = you");
    assert_eq!(message_verb("spawn"), "started");
}
