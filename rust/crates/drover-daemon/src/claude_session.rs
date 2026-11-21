//! Which Claude Code conversation a pane runs, so a restart resumes that exact one (`claude --resume <id>`).
//! Port of `claude_session_id_probe.py`. Claude's own files, not an API: anything odd gives None.

use std::path::PathBuf;
use std::sync::LazyLock;

use regex::Regex;

// A UUID only: the id goes into a command line, so nothing else may get through.
static SESSION_ID: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$").unwrap()
});

pub fn claude_config_dir() -> PathBuf {
    std::env::var_os("CLAUDE_CONFIG_DIR")
        .filter(|v| !v.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| dirs::home_dir().unwrap_or_default().join(".claude"))
}

/// Conversation id of the first pid that is a running Claude Code process.
pub fn running_session_id(pids: impl IntoIterator<Item = i32>) -> Option<String> {
    let base = claude_config_dir();
    pids.into_iter().find_map(|pid| {
        let text = std::fs::read_to_string(base.join("sessions").join(format!("{pid}.json"))).ok()?;
        let v: serde_json::Value = serde_json::from_str(&text).ok()?;
        let sid = v.get("sessionId")?.as_str()?;
        is_session_id(sid).then(|| sid.to_string())
    })
}

/// A UUID and nothing else: session ids end up in a resume command line (Claude and Codex both use UUIDs).
pub fn is_session_id(sid: &str) -> bool {
    SESSION_ID.is_match(sid)
}

/// `claude --resume` fails on a conversation with no message yet; its transcript appears with the first one.
pub fn has_transcript(sid: &str) -> bool {
    let projects = claude_config_dir().join("projects");
    std::fs::read_dir(projects).into_iter().flatten().flatten().any(|d| d.path().join(format!("{sid}.jsonl")).is_file())
}

pub fn resume_command(sid: &str) -> String {
    format!("claude --resume {sid}")
}
