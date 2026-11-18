//! Translate ids between a remote daemon ("%3") and the hub's combined view ("vps-1:%3"). Port of `id_prefixing.py`.

use serde_json::{Map, Value};

const ID_KEYS: &[&str] = &["id", "space_id", "tab_id", "parent", "focused", "pane", "target", "source", "split_from", "previous_tab"];
/// The first one present decides which machine handles a call.
const ROUTE_KEYS: &[&str] = &["machine", "pane", "tab", "space", "tab_id"];
const PEER_ID_KEYS: &[&str] = &["pane", "target", "tab", "tab_id", "space", "split_from"];
const STRIP_EXTRA: &[&str] = &["panes", "tab", "space"];

fn text(v: &Value) -> Option<String> {
    match v {
        Value::Null | Value::Bool(false) => None,
        Value::String(s) if s.is_empty() => None,
        Value::String(s) => Some(s.clone()),
        other => Some(other.to_string()),
    }
}

pub fn route_of(params: &Value) -> String {
    ROUTE_KEYS.iter().find_map(|k| text(&params[*k])).unwrap_or_default()
}

/// Id params of a call routed to `alias` that name another machine's objects (e.g. swap vps:%3 with local %2).
/// Forwarded unchanged they would silently resolve to the remote machine's own, unrelated %2.
pub fn foreign_ids(params: &Value, alias: &str) -> Vec<String> {
    let marker = format!("{alias}:");
    PEER_ID_KEYS.iter().filter_map(|k| {
        let v = params[*k].as_str().filter(|v| !v.is_empty() && !v.starts_with(&marker))?;
        Some(format!("{k}={v}"))
    }).collect()
}

pub fn prefix_ids(value: &Value, alias: &str) -> Value {
    prefix(value, alias, None)
}

fn prefix(value: &Value, alias: &str, key: Option<&str>) -> Value {
    match value {
        Value::Object(o) => Value::Object(o.iter().map(|(k, v)| (k.clone(), prefix(v, alias, Some(k)))).collect()),
        Value::Array(a) => Value::Array(a.iter().map(|v| prefix(v, alias, key)).collect()),
        Value::String(s) if key.is_some_and(|k| ID_KEYS.contains(&k)) && !s.is_empty() && !s.contains(':') => {
            Value::String(format!("{alias}:{s}"))
        }
        other => other.clone(),
    }
}

/// Remove `alias:` only from id-carrying fields, never from user text like a prompt. Drops `machine` keys.
pub fn strip_ids(value: &Value, alias: &str) -> Value {
    strip(value, &format!("{alias}:"), None)
}

fn strip(value: &Value, marker: &str, key: Option<&str>) -> Value {
    match value {
        Value::Object(o) => Value::Object(o.iter().filter(|(k, _)| *k != "machine")
            .map(|(k, v)| (k.clone(), strip(v, marker, Some(k)))).collect::<Map<_, _>>()),
        Value::Array(a) => Value::Array(a.iter().map(|v| strip(v, marker, key)).collect()),
        Value::String(s) if key.is_some_and(|k| ID_KEYS.contains(&k) || STRIP_EXTRA.contains(&k)) && s.starts_with(marker) => {
            Value::String(s[marker.len()..].to_string())
        }
        other => other.clone(),
    }
}

pub fn tag_machine(mut snapshot: Value, alias: &str) -> Value {
    for key in ["panes", "spaces", "stopped"] {
        for item in snapshot[key].as_array_mut().into_iter().flatten() {
            if let Some(o) = item.as_object_mut() {
                o.insert("machine".into(), Value::String(alias.into()));
            }
        }
    }
    snapshot
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn snapshot() -> Value {
        json!({
            "spaces": [{"id": "s1", "name": "repo", "cwd": "C:/repo"}],
            "tabs": [{"id": "t1", "space_id": "s1", "focused": "%3",
                      "layout": {"split": "row", "ratio": 0.5, "a": {"pane": "%3"}, "b": {"pane": "%4"}}}],
            "panes": [{"id": "%3", "name": "claude", "tab_id": "t1", "space_id": "s1", "parent": null, "state": "idle"}],
        })
    }

    #[test]
    fn prefix_adds_alias_to_id_fields_only() {
        let out = prefix_ids(&snapshot(), "vps");
        assert_eq!(out["spaces"][0]["id"], "vps:s1");
        assert_eq!(out["tabs"][0]["space_id"], "vps:s1");
        assert_eq!(out["tabs"][0]["focused"], "vps:%3");
        assert_eq!(out["tabs"][0]["layout"]["a"]["pane"], "vps:%3");
        assert!(out["panes"][0]["parent"].is_null());
        assert_eq!(out["panes"][0]["name"], "claude");
        assert_eq!(out["spaces"][0]["cwd"], "C:/repo");
        assert_eq!(prefix_ids(&json!({"id": "other:%9", "parent": ""}), "vps"), json!({"id": "other:%9", "parent": ""}));
    }

    #[test]
    fn strip_removes_alias_and_machine_but_not_user_text() {
        assert_eq!(strip_ids(&json!({"id": "vps:%3", "machine": "vps", "name": "keep-me"}), "vps"), json!({"id": "%3", "name": "keep-me"}));
        let msg = json!({"t": "rpc", "params": {"pane": "vps:%3", "text": "vps: deploy now", "panes": ["vps:%1", "vps:%2"]}});
        assert_eq!(strip_ids(&msg, "vps"), json!({"t": "rpc", "params": {"pane": "%3", "text": "vps: deploy now", "panes": ["%1", "%2"]}}));
        let layout = json!({"tab": "vps:t1", "layout": {"split": "row", "a": {"pane": "vps:%1"}, "b": {"pane": "vps:%2"}}});
        assert_eq!(strip_ids(&layout, "vps"), json!({"tab": "t1", "layout": {"split": "row", "a": {"pane": "%1"}, "b": {"pane": "%2"}}}));
        assert_eq!(strip_ids(&prefix_ids(&snapshot(), "vps"), "vps"), snapshot());
    }

    #[test]
    fn routing_tagging_and_foreign_ids() {
        let tagged = tag_machine(json!({"panes": [{"id": "%1"}], "spaces": [{"id": "s1"}], "stopped": [{"id": "%2"}], "tabs": []}), "lab");
        assert_eq!((&tagged["panes"][0]["machine"], &tagged["spaces"][0]["machine"], &tagged["stopped"][0]["machine"]),
                   (&json!("lab"), &json!("lab"), &json!("lab")));
        assert_eq!(route_of(&json!({"pane": "vps:%3", "tab": "t1"})), "vps:%3");
        assert_eq!(route_of(&json!({"machine": "", "space": "lab:s1"})), "lab:s1");
        assert_eq!(foreign_ids(&json!({"pane": "vps:%3", "target": "%2"}), "vps"), ["target=%2"]);
    }
}
