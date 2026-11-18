//! How panes are launched: default shell, argv resolution on Windows, PATH with `dr` first, and the per-pane
//! Claude Code hooks that report sub-agents. Ports of `pty_backend_factory.py`, `self_command.pane_path` and
//! `claude_subagent_hooks.py`.

use std::path::{Path, PathBuf};

use drover_core::launch_command::split_command;

pub fn default_shell(configured: &str) -> Vec<String> {
    if !configured.trim().is_empty() {
        return split_command(configured).unwrap_or_else(|| vec![configured.to_string()]);
    }
    if cfg!(windows) {
        for name in ["pwsh.exe", "powershell.exe"] {
            if let Some(path) = which(name) {
                return vec![path.to_string_lossy().into_owned(), "-NoLogo".into()];
            }
        }
        return vec![std::env::var("COMSPEC").unwrap_or_else(|_| "cmd.exe".into())];
    }
    vec![std::env::var("SHELL").unwrap_or_else(|_| "/bin/bash".into()), "-l".into()]
}

/// Find a program on PATH (with PATHEXT on Windows).
pub fn which(name: &str) -> Option<PathBuf> {
    let candidate = Path::new(name);
    if candidate.components().count() > 1 {
        return candidate.is_file().then(|| candidate.to_path_buf());
    }
    let exts: Vec<String> = if cfg!(windows) {
        let pathext = std::env::var("PATHEXT").unwrap_or_else(|_| ".COM;.EXE;.BAT;.CMD".into());
        std::iter::once(String::new()).chain(pathext.split(';').map(str::to_lowercase)).collect()
    } else {
        vec![String::new()]
    };
    let path = std::env::var_os("PATH")?;
    std::env::split_paths(&path).find_map(|dir| {
        exts.iter().map(|ext| dir.join(format!("{name}{ext}"))).find(|p| p.is_file())
    })
}

/// On Windows resolve `claude` to `claude.cmd`/`.exe` so ConPTY can start it; elsewhere unchanged.
pub fn resolve_argv(argv: Vec<String>) -> Vec<String> {
    if !cfg!(windows) || argv.is_empty() {
        return argv;
    }
    let Some(found) = which(&argv[0]) else { return argv };
    let found = found.to_string_lossy().into_owned();
    let lower = found.to_lowercase();
    if lower.ends_with(".cmd") || lower.ends_with(".bat") {
        let comspec = std::env::var("COMSPEC").unwrap_or_else(|_| "cmd.exe".into());
        return [comspec, "/c".into(), found].into_iter().chain(argv.into_iter().skip(1)).collect();
    }
    std::iter::once(found).chain(argv.into_iter().skip(1)).collect()
}

/// Folder of the running `dr` binary, so agents in panes can call `dr`.
pub fn exe_dir() -> Option<PathBuf> {
    std::env::current_exe().ok().and_then(|p| p.parent().map(Path::to_path_buf))
}

pub fn pane_path(current: &str) -> String {
    let Some(dir) = exe_dir() else { return current.to_string() };
    let sep = if cfg!(windows) { ";" } else { ":" };
    let dir = dir.to_string_lossy();
    if current.split(sep).any(|p| p == dir) {
        return current.to_string();
    }
    if current.is_empty() { dir.into_owned() } else { format!("{dir}{sep}{current}") }
}

/// Variables that belong to one running Claude Code session. A daemon started from inside an agent (e.g. `dr`
/// autostarting it) would otherwise hand them to every pane, and claude there believes it is a child session
/// (transcripts off, hooks talking to the other session's socket). User config such as CLAUDE_CONFIG_DIR stays.
pub(crate) fn is_session_var(key: &str) -> bool {
    key == "CLAUDECODE" || key == "CLAUDE_PID" || key == "CLAUDE_EFFORT" || key.starts_with("CLAUDE_CODE_")
}

/// Environment of a new pane: ours (minus another agent session's markers) plus terminal type, pane id and PATH.
pub fn pane_env(pane_id: &str) -> Vec<(String, String)> {
    let mut env: Vec<(String, String)> = std::env::vars()
        .filter(|(k, _)| !matches!(k.as_str(), "TERM" | "COLORTERM" | "DR_PANE_ID" | "DROVER" | "PATH") && !is_session_var(k))
        .collect();
    env.push(("TERM".into(), "xterm-256color".into()));
    env.push(("COLORTERM".into(), "truecolor".into()));
    env.push(("DR_PANE_ID".into(), pane_id.into()));
    env.push(("DROVER".into(), "1".into()));
    env.push(("PATH".into(), pane_path(&std::env::var("PATH").unwrap_or_default())));
    env
}

/// Shell command line for the Claude hook (forward slashes + double quotes work in Git Bash, cmd and sh).
fn hook_command() -> String {
    let exe = std::env::current_exe().map(|p| p.to_string_lossy().replace('\\', "/")).unwrap_or_else(|_| "dr".into());
    format!("\"{exe}\" hook claude")
}

/// Write (only when it changed) and return the settings file holding drover's sub-agent hooks.
fn hooks_settings_file() -> std::io::Result<PathBuf> {
    let hook = serde_json::json!([{"hooks": [{"type": "command", "command": hook_command(), "timeout": 10}]}]);
    let body = serde_json::to_string_pretty(&serde_json::json!({"hooks": {"SubagentStart": hook, "SubagentStop": hook}}))
        .map_err(std::io::Error::other)?;
    let path = crate::paths::state_dir().join("claude-subagent-hooks.json");
    if std::fs::read_to_string(&path).ok().as_deref() != Some(body.as_str()) {
        std::fs::write(&path, body)?;
    }
    Ok(path)
}

/// argv of a `claude` pane with `--settings <file>` right after the program; anything else unchanged.
pub fn with_subagent_hooks(argv: Vec<String>) -> Vec<String> {
    let is_claude = argv
        .first()
        .and_then(|a| Path::new(a).file_stem().and_then(|s| s.to_str()).map(str::to_lowercase))
        .is_some_and(|s| s == "claude");
    if !is_claude || argv.iter().any(|a| a == "--settings") {
        return argv;
    }
    match hooks_settings_file() {
        Ok(file) => {
            let mut out = vec![argv[0].clone(), "--settings".into(), file.to_string_lossy().into_owned()];
            out.extend(argv.into_iter().skip(1));
            out
        }
        Err(_) => argv, // state dir not writable: run claude without the Flow lanes rather than not at all
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn claude_session_markers_are_dropped_but_user_config_stays() {
        for k in ["CLAUDECODE", "CLAUDE_CODE_CHILD_SESSION", "CLAUDE_CODE_MESSAGING_SOCKET", "CLAUDE_PID"] {
            assert!(is_session_var(k), "{k}");
        }
        for k in ["CLAUDE_CONFIG_DIR", "ANTHROPIC_API_KEY", "HOME"] {
            assert!(!is_session_var(k), "{k}");
        }
    }
}
