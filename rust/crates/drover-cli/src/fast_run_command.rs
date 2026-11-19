//! `dr run`: same params and output as `cli_commands_agents.cmd_run`. Role templates (`dr run reviewer "task"`)
//! go to Python, which owns the template format. Without `--bg` the pane is created here and the terminal is
//! attached by the Python CLI (`dr attach <id>`), which is what `cmd_run` does after creating it.

use serde_json::{Map, Value, json};

use crate::drover_paths;
use crate::fast_commands::{DEFAULT_RPC_TIMEOUT, Failure, field, rpc};
use crate::python_command_line;

#[derive(Debug, PartialEq, Default)]
pub struct RunArgs {
    pub bg: bool,
    pub split: bool,
    pub outlive_parent: bool,
    pub name: String,
    pub cwd: String,
    pub on: String,
    pub worktree: String,
    /// argparse REMAINDER: every token from the first one that is not a run option, verbatim (`--` included).
    pub command: Vec<String>,
}

/// argparse for `dr run`: options only before the command. None (-> Python) for unknown options, `--x=` on a
/// flag, or a value that is missing or looks like an option.
pub fn parse(rest: &[String]) -> Option<RunArgs> {
    let mut a = RunArgs::default();
    let mut i = 0;
    while i < rest.len() {
        let word = &rest[i];
        if word == "--" || word == "-" || !word.starts_with('-') {
            break;
        }
        let (flag, inline) = match word.split_once('=') {
            Some((f, v)) => (f, Some(v.to_string())),
            None => (word.as_str(), None),
        };
        let slot = match flag {
            "--bg" | "--split" | "--outlive-parent" if inline.is_none() => {
                match flag {
                    "--bg" => a.bg = true,
                    "--split" => a.split = true,
                    _ => a.outlive_parent = true,
                }
                i += 1;
                continue;
            }
            "--name" => &mut a.name,
            "--cwd" => &mut a.cwd,
            "--on" => &mut a.on,
            "--worktree" => &mut a.worktree,
            _ => return None,
        };
        *slot = match inline {
            Some(v) => v,
            None => {
                i += 1;
                let next = rest.get(i)?;
                if next.starts_with('-') && next != "-" {
                    return None;
                }
                next.clone()
            }
        };
        i += 1;
    }
    a.command = rest[i..].to_vec();
    Some(a)
}

/// `load_template(words[0])` would find a file: Python expands it.
fn is_template(command: &[String]) -> bool {
    let words = match command.split_first() {
        Some((first, rest)) if first == "--" => rest,
        _ => command,
    };
    let Some(name) = words.first() else { return false };
    let valid = !name.is_empty() && name.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-');
    valid && drover_paths::config_dir().join("templates").join(format!("{name}.md")).is_file()
}

pub enum RunResult {
    /// `--bg`: print the pane id.
    Printed(String),
    /// Hand the command to Python as is (template, odd cwd).
    Delegate,
    /// Attach this pane's terminal through the Python CLI.
    Attach(String),
}

pub fn run(a: RunArgs) -> Result<RunResult, Failure> {
    if is_template(&a.command) {
        return Ok(RunResult::Delegate);
    }
    let cwd = if !a.cwd.is_empty() {
        a.cwd.clone()
    } else {
        match std::env::current_dir().ok().and_then(|d| d.to_str().map(str::to_string)) {
            Some(d) => d,
            None => return Ok(RunResult::Delegate), // non-UTF-8 folder: Python decodes it its own way
        }
    };
    let mut params = Map::new();
    params.insert("command".into(), json!(python_command_line::join(&a.command)));
    params.insert("name".into(), json!(a.name));
    params.insert("cwd".into(), json!(cwd));
    if !a.on.is_empty() {
        params.insert("machine".into(), json!(a.on));
        params.insert("cwd".into(), json!(a.cwd)); // remote default = remote home
    }
    if !a.worktree.is_empty() {
        params.insert("worktree".into(), json!({"task": a.worktree}));
    }
    if a.outlive_parent {
        params.insert("outlive_parent".into(), json!(true));
    }
    if a.split
        && let Ok(caller) = std::env::var("DR_PANE_ID")
        && !caller.is_empty()
    {
        let state = rpc("state.get", json!({}), DEFAULT_RPC_TIMEOUT)?;
        let panes = state.get("panes").and_then(Value::as_array).ok_or(Failure::Unexpected)?;
        if let Some(pane) = panes.iter().find(|p| p.get("id").and_then(Value::as_str) == Some(caller.as_str())) {
            params.insert("tab_id".into(), pane.get("tab_id").cloned().unwrap_or(Value::Null));
            params.insert("split_from".into(), json!(caller));
        }
    }
    let pane = rpc("pane.create", Value::Object(params), DEFAULT_RPC_TIMEOUT)?;
    let id = field(&pane, "id")?;
    Ok(if a.bg { RunResult::Printed(id) } else { RunResult::Attach(id) })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn p(words: &[&str]) -> Option<RunArgs> {
        parse(&words.iter().map(|s| s.to_string()).collect::<Vec<_>>())
    }

    #[test]
    fn remainder_starts_at_the_first_non_option_like_argparse() {
        // each case checked against argparse (cli_main.build_parser) on CPython 3.12
        let a = p(&["--bg", "--", "claude", "x"]).unwrap();
        assert!(a.bg && a.command == ["--", "claude", "x"]);
        let a = p(&["--bg", "claude", "--name", "x"]).unwrap();
        assert!(a.name.is_empty() && a.command == ["claude", "--name", "x"]);
        let a = p(&["--name=a", "--cwd", "C:\\w", "claude", "-p", "hi there"]).unwrap();
        assert_eq!((a.name.as_str(), a.cwd.as_str()), ("a", "C:\\w"));
        assert_eq!(a.command, ["claude", "-p", "hi there"]);
        assert_eq!(p(&["--bg"]).unwrap().command, Vec::<String>::new());
        assert_eq!(p(&["-", "x"]).unwrap().command, ["-", "x"]);
    }

    #[test]
    fn odd_options_go_to_python() {
        assert_eq!(p(&["-x"]), None);
        assert_eq!(p(&["--bg=1"]), None);
        assert_eq!(p(&["--name"]), None);
        assert_eq!(p(&["--name", "--bg"]), None);
        assert_eq!(p(&["--help"]), None);
        assert_eq!(p(&["--na", "x"]), None);
    }
}
