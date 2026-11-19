//! `dr ls`, `dr ls --json`, `dr ls --names`: same table and JSON as `cli_commands_agents.cmd_ls`.

use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde_json::{Map, Value};

use crate::daemon_rpc;
use crate::fast_commands::{DEFAULT_RPC_TIMEOUT, Failure, field, rpc};
use crate::python_json::{dumps_indent1, py_str};
use crate::python_output::{ljust, print_out};

/// `STATE_LABEL.get(state, state)`: only "blocked" reads differently.
pub fn state_label(state: &str) -> String {
    if state == "blocked" { "needs you" } else { state }.to_string()
}

/// `_age`: whole seconds since `created_at`, as 3d / 4h / 5m / 6s.
fn age(elapsed: f64) -> String {
    let seconds = if elapsed > 0.0 { elapsed.trunc() as u64 } else { 0 };
    for (unit, size) in [("d", 86400), ("h", 3600), ("m", 60)] {
        if seconds >= size {
            return format!("{}{unit}", seconds / size);
        }
    }
    format!("{seconds}s")
}

/// (id, name) of every space in a `spaces` list.
fn spaces_of(list: Option<&Value>) -> Vec<(Value, Value)> {
    list.and_then(Value::as_array).into_iter().flatten()
        .map(|s| (s.get("id").cloned().unwrap_or(Value::Null), s.get("name").cloned().unwrap_or(Value::Null)))
        .collect()
}

fn snapshot_list(machine: &Value, key: &str) -> Vec<Value> {
    machine.get("snapshot").and_then(|s| s.get(key)).and_then(Value::as_array).cloned().unwrap_or_default()
}

/// Local panes plus every remote machine's snapshot panes, as text (table or indent=1 JSON).
pub fn ls(json_out: bool) -> Result<String, Failure> {
    let state = rpc("state.get", Value::Object(Map::new()), DEFAULT_RPC_TIMEOUT)?;
    let machines = state.get("machines").and_then(Value::as_array).cloned().unwrap_or_default();
    let mut panes = state.get("panes").and_then(Value::as_array).cloned().ok_or(Failure::Unexpected)?;
    for m in &machines {
        panes.extend(snapshot_list(m, "panes"));
    }
    if json_out {
        return Ok(dumps_indent1(&Value::Array(panes)));
    }
    let mut spaces = spaces_of(state.get("spaces"));
    for m in &machines {
        spaces.extend(spaces_of(Some(&Value::Array(snapshot_list(m, "spaces")))));
    }
    let now = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs_f64()).unwrap_or(0.0);
    let mut rows = vec![["ID", "NAME", "AGENT", "STATE", "SPACE", "MACHINE", "AGE"].map(String::from)];
    for p in &panes {
        let space_id = p.get("space_id").cloned().unwrap_or(Value::Null);
        // a dict built with update(): the last space with that id wins
        let space = spaces.iter().rev().find(|(id, _)| *id == space_id).map(|(_, n)| py_str(n)).unwrap_or_default();
        let created = p.get("created_at").and_then(Value::as_f64).ok_or(Failure::Unexpected)?;
        rows.push([field(p, "id")?, field(p, "name")?, field(p, "kind")?, state_label(&field(p, "state")?), space,
                   p.get("machine").map(py_str).unwrap_or_else(|| "local".into()), age(now - created)]);
    }
    let widths: Vec<usize> = (0..7).map(|i| rows.iter().map(|r| r[i].chars().count()).max().unwrap_or(0)).collect();
    let lines: Vec<String> = rows.iter()
        .map(|r| r.iter().zip(&widths).map(|(c, w)| ljust(c, *w)).collect::<Vec<_>>().join("  ").trim_end().to_string())
        .collect();
    Ok(lines.join("\n"))
}

/// `dr ls --names` for shell completion: never starts the daemon, prints nothing on any failure.
pub fn print_names() -> i32 {
    let Ok(state) = daemon_rpc::call("state.get", Map::new(), Duration::from_secs(2)) else {
        return 0;
    };
    let mut names: Vec<String> = state.get("panes").and_then(Value::as_array).into_iter().flatten()
        .filter_map(|p| p.get("name").map(py_str)).collect();
    names.sort();
    names.dedup();
    print_out(&names.join("\n"));
    0
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn age_and_labels_match_python() {
        assert_eq!(age(-3.0), "0s");
        assert_eq!(age(59.9), "59s");
        assert_eq!(age(61.0), "1m");
        assert_eq!(age(7200.5), "2h");
        assert_eq!(age(90000.0), "1d");
        assert_eq!(state_label("blocked"), "needs you");
        assert_eq!(state_label("weird"), "weird");
    }
}
