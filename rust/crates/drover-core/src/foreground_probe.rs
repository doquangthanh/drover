//! Which program holds a pane's terminal right now (Herdr-style agent detection, Linux via /proc).
//! Port of `drover/core/foreground_process_probe.py`. The foreground process group itself comes from
//! `Pty::foreground_pgid` (tcgetpgrp). Windows has no such notion: see `windows_process_tree`.

use std::path::Path;

/// Executable names that differ from the rule-set id they belong to.
const ALIASES: [(&str, &str); 4] =
    [("claude-code", "claude"), ("open-code", "opencode"), ("opencode2", "opencode"), ("gemini-cli", "gemini")];
/// Interpreters that run an agent as a script: the agent is the first non-option argument.
const RUNTIMES: [&str; 9] = ["node", "bun", "deno", "python", "python3", "sh", "bash", "zsh", "fish"];
const SHELLS: [&str; 4] = ["sh", "bash", "zsh", "fish"];
const SCRIPT_EXTS: [&str; 5] = [".js", ".mjs", ".cjs", ".ts", ".py"];
/// Windows program suffixes: `claude.exe`, `node.exe`, `codex.cmd` name the same thing as on Linux.
const PROGRAM_EXTS: [&str; 3] = [".exe", ".cmd", ".bat"];

fn base(arg: &str) -> String {
    // Split on both separators: Windows command lines use `\`, and the tests run on every platform.
    let name = arg.trim_end_matches(['/', '\\']).rsplit(['/', '\\']).next().unwrap_or(arg).to_lowercase();
    for ext in SCRIPT_EXTS.iter().chain(&PROGRAM_EXTS) {
        if let Some(stem) = name.strip_suffix(ext) {
            return stem.to_string();
        }
    }
    name
}

/// Rule-set id for a command line: `claude`, `/usr/bin/codex`, `node .../bin/claude`, `sh -c gemini`.
pub fn agent_kind_from_argv(argv: &[String], kinds: &[&str]) -> Option<String> {
    let first = base(argv.first()?);
    let mut names = vec![first.clone()];
    if RUNTIMES.contains(&first.as_str()) {
        let mut rest: Vec<String> = argv[1..].iter().filter(|a| !a.starts_with('-')).cloned().collect();
        if SHELLS.contains(&first.as_str())
            && let Some(i) = argv[1..].iter().position(|a| a == "-c")
        {
            rest = argv.get(i + 2).and_then(|s| s.split_whitespace().next()).map(String::from).into_iter().collect();
        }
        names.extend(rest.first().map(|a| base(a)));
    }
    names.into_iter().find_map(|name| {
        let kind = ALIASES.iter().find(|(from, _)| *from == name).map(|(_, to)| to.to_string()).unwrap_or(name);
        (kinds.contains(&kind.as_str()) && kind != "shell").then_some(kind)
    })
}

pub fn process_argv(pid: i32) -> Vec<String> {
    let dir = format!("/proc/{pid}");
    let Ok(raw) = std::fs::read(format!("{dir}/cmdline")) else { return vec![] };
    let argv: Vec<String> =
        raw.split(|b| *b == 0).filter(|a| !a.is_empty()).map(|a| String::from_utf8_lossy(a).into_owned()).collect();
    if !argv.is_empty() {
        return argv;
    }
    // kernel threads, zombies
    std::fs::read_to_string(format!("{dir}/comm")).map(|c| vec![c.trim().to_string()]).unwrap_or_default()
}

/// Fields after the `(comm)` part of /proc/<pid>/stat (state is index 0, ppid 1, pgrp 2).
fn stat_fields(pid: &str) -> Option<Vec<String>> {
    let stat = std::fs::read_to_string(format!("/proc/{pid}/stat")).ok()?;
    let after = stat.get(stat.rfind(')')? + 2..)?;
    Some(after.split_whitespace().map(String::from).collect())
}

/// Every process in the group, leader first.
pub fn group_members(pgid: i32) -> Vec<i32> {
    let mut members = vec![pgid];
    let Ok(entries) = std::fs::read_dir("/proc") else { return members };
    for entry in entries.flatten() {
        let name = entry.file_name().to_string_lossy().into_owned();
        let Ok(pid) = name.parse::<i32>() else { continue };
        if pid != pgid && stat_fields(&name).and_then(|f| f.get(2)?.parse::<i32>().ok()) == Some(pgid) {
            members.push(pid);
        }
    }
    members
}

pub fn process_cwd(pid: i32) -> Option<String> {
    std::fs::read_link(format!("/proc/{pid}/cwd")).ok().map(|p| p.to_string_lossy().into_owned())
}

/// Agent running in the foreground group: the leader first, then any other member.
pub fn foreground_agent_kind(pgid: i32, kinds: &[&str]) -> Option<String> {
    group_members(pgid).into_iter().find_map(|pid| agent_kind_from_argv(&process_argv(pid), kinds))
}

/// Agent a pane's shell is running now, as (pid, rule-set id); None while it is just the shell. One entry point for
/// every platform, only the process lookup differs: Linux asks the terminal for its foreground group (`fg_pgid`),
/// Windows has none and looks at the programs the shell started.
pub fn running_agent(shell_pid: Option<u32>, fg_pgid: Option<i32>, kinds: &[&str]) -> Option<(u32, String)> {
    #[cfg(windows)]
    {
        let _ = fg_pgid;
        crate::windows_process_tree::descendant_agent(shell_pid?, kinds)
    }
    #[cfg(not(windows))]
    {
        let pgid = fg_pgid.filter(|g| Some(*g as u32) != shell_pid)?; // the shell itself in front: no agent
        foreground_agent_kind(pgid, kinds).map(|kind| (pgid as u32, kind))
    }
}

/// Where the pane is now: cwd of the foreground program, else of the shell (Herdr's follow_cwd).
pub fn follow_cwd(fg_pgid: Option<i32>, shell_pid: Option<i32>) -> Option<String> {
    [fg_pgid, shell_pid].into_iter().flatten().find_map(|pid| process_cwd(pid).filter(|c| Path::new(c).is_dir()))
}

#[cfg(test)]
mod tests {
    use super::*;

    const KINDS: [&str; 5] = ["claude", "codex", "gemini", "opencode", "shell"];

    #[test]
    fn agent_kind_from_argv_table() {
        let cases: &[(&[&str], Option<&str>)] = &[
            (&["claude"], Some("claude")),
            (&["/home/me/.local/bin/claude", "--continue"], Some("claude")),
            (&["claude-code"], Some("claude")),
            (&["node", "--no-warnings", "/usr/lib/node_modules/@openai/codex/bin/codex.js"], Some("codex")),
            (&["/bin/sh", "/tmp/x/gemini"], Some("gemini")),
            (&["bash", "-c", "opencode run"], Some("opencode")),
            (&[r"C:\Users\me\.local\bin\claude.exe"], Some("claude")),
            (&[r"C:\Program Files\nodejs\node.exe", r"C:\npm\node_modules\@openai\codex\bin\codex.js"], Some("codex")),
            (&["node.exe", "server.js"], None),
            (&["vim", "claude.md"], None),
            (&["zsh"], None),
            (&["node", "server.js"], None),
            (&[], None),
        ];
        for (argv, kind) in cases {
            let argv: Vec<String> = argv.iter().map(|s| s.to_string()).collect();
            assert_eq!(agent_kind_from_argv(&argv, &KINDS).as_deref(), *kind, "{argv:?}");
        }
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn own_process_is_readable() {
        let pid = std::process::id() as i32;
        assert!(!process_argv(pid).is_empty());
        assert!(process_cwd(pid).is_some());
        assert_eq!(follow_cwd(None, Some(pid)), process_cwd(pid));
    }
}
