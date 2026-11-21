//! Which Codex conversation a pane runs, so a restart resumes that one (`codex resume <id>`) instead of the
//! machine's newest (`codex resume --last`, which sends every Codex pane into the same conversation).
//! Codex writes `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<time>-<uuid>.jsonl`; the first line is the session
//! meta (`{"type":"session_meta","payload":{"id","cwd",..}}`, older files: the fields at top level).
//! Codex's own files, not an API: anything odd gives None.

use std::io::{BufRead, BufReader, Read};
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime};

use crate::claude_session::is_session_id;

const FIRST_LINE_CAP: u64 = 256 * 1024; // the meta line carries the instructions; never read a whole transcript

pub fn codex_home() -> PathBuf {
    std::env::var_os("CODEX_HOME")
        .filter(|v| !v.is_empty())
        .map(PathBuf::from)
        .unwrap_or_else(|| dirs::home_dir().unwrap_or_default().join(".codex"))
}

pub fn resume_command(sid: &str) -> String {
    format!("codex resume {sid}")
}

/// Folder spelling that compares equal across `C:\Work\` and `c:/work` (case only folds on Windows).
pub fn same_folder(a: &str, b: &str) -> bool {
    let norm = |p: &str| {
        let p = p.replace('\\', "/");
        let p = p.trim_end_matches('/').to_string();
        if cfg!(windows) { p.to_lowercase() } else { p }
    };
    norm(a) == norm(b)
}

/// Newest conversation (by the creation time in its file name) started in `cwd` and written since `since`.
/// The caller makes sure no other Codex pane runs in that folder, so "newest there" is this pane's.
pub fn newest_session_in(cwd: &str, since: SystemTime) -> Option<String> {
    let mut best: Option<(String, String)> = None; // (file name, id)
    for file in recent_rollouts(&codex_home().join("sessions"), since) {
        let name = file.file_name().and_then(|n| n.to_str()).unwrap_or("").to_string();
        if best.as_ref().is_some_and(|(b, _)| *b >= name) {
            continue;
        }
        if let Some((id, folder)) = session_meta(&file)
            && same_folder(&folder, cwd)
        {
            best = Some((name, id));
        }
    }
    best.map(|(_, id)| id)
}

/// `rollout-*.jsonl` under sessions/YYYY/MM/DD modified since `since`; day folders older than a day are skipped.
fn recent_rollouts(root: &Path, since: SystemTime) -> Vec<PathBuf> {
    let fresh = |p: &Path, slack: Duration| {
        p.metadata().and_then(|m| m.modified()).is_ok_and(|t| t + slack >= since)
    };
    let children = |p: &Path| -> Vec<PathBuf> {
        std::fs::read_dir(p).into_iter().flatten().flatten().map(|e| e.path()).collect()
    };
    let day = Duration::from_secs(86_400);
    children(root).into_iter().filter(|p| p.is_dir())
        .flat_map(|year| children(&year)).filter(|p| p.is_dir())
        .flat_map(|month| children(&month)).filter(|p| p.is_dir() && fresh(p, day))
        .flat_map(|d| children(&d))
        .filter(|f| {
            let name = f.file_name().and_then(|n| n.to_str()).unwrap_or("");
            name.starts_with("rollout-") && name.ends_with(".jsonl") && fresh(f, Duration::ZERO)
        })
        .collect()
}

/// (session id, cwd) from a rollout file's first line.
fn session_meta(file: &Path) -> Option<(String, String)> {
    let mut line = String::new();
    BufReader::new(std::fs::File::open(file).ok()?.take(FIRST_LINE_CAP)).read_line(&mut line).ok()?;
    parse_meta_line(&line)
}

fn parse_meta_line(line: &str) -> Option<(String, String)> {
    let v: serde_json::Value = serde_json::from_str(line.trim()).ok()?;
    let meta = v.get("payload").unwrap_or(&v);
    let id = meta.get("id")?.as_str()?;
    let cwd = meta.get("cwd")?.as_str()?;
    is_session_id(id).then(|| (id.to_string(), cwd.to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    const ID: &str = "0199a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b";

    #[test]
    fn reads_new_and_old_meta_lines() {
        let new = format!(r#"{{"timestamp":"t","type":"session_meta","payload":{{"id":"{ID}","cwd":"C:\\work"}}}}"#);
        assert_eq!(parse_meta_line(&new), Some((ID.into(), r"C:\work".into())));
        let old = format!(r#"{{"id":"{ID}","cwd":"/home/me/app","instructions":"x"}}"#);
        assert_eq!(parse_meta_line(&old).map(|m| m.1), Some("/home/me/app".into()));
        // Not a UUID (it goes into a command line), or no folder: ignored.
        assert_eq!(parse_meta_line(r#"{"payload":{"id":"x; rm -rf /","cwd":"/"}}"#), None);
        assert_eq!(parse_meta_line(&format!(r#"{{"payload":{{"id":"{ID}"}}}}"#)), None);
    }

    #[test]
    fn folders_compare_across_separators() {
        assert!(same_folder("/home/me/app/", "/home/me/app"));
        assert!(same_folder(r"C:\work\app", "C:/work/app"));
        assert!(!same_folder("/home/me/app", "/home/me/app2"));
        assert_eq!(resume_command(ID), format!("codex resume {ID}"));
    }

    #[test]
    fn picks_the_newest_conversation_of_the_folder() {
        let home = std::env::temp_dir().join(format!("drover-codex-test-{}", std::process::id()));
        let day = home.join("sessions/2026/11/21");
        std::fs::create_dir_all(&day).unwrap();
        let other = "0199a1b2-c3d4-7e5f-8a9b-000000000001";
        let newer = "0199a1b2-c3d4-7e5f-8a9b-000000000002";
        let meta = |id: &str, cwd: &str| format!(r#"{{"type":"session_meta","payload":{{"id":"{id}","cwd":"{cwd}"}}}}"#) + "\n";
        std::fs::write(day.join(format!("rollout-2026-11-21T10-00-00-{ID}.jsonl")), meta(ID, "/w/app")).unwrap();
        std::fs::write(day.join(format!("rollout-2026-11-21T11-00-00-{newer}.jsonl")), meta(newer, "/w/app")).unwrap();
        std::fs::write(day.join(format!("rollout-2026-11-21T12-00-00-{other}.jsonl")), meta(other, "/w/other")).unwrap();
        let since = SystemTime::now() - Duration::from_secs(60);
        let found = {
            // CODEX_HOME is process-wide; this is the only test that sets it.
            unsafe { std::env::set_var("CODEX_HOME", &home) };
            newest_session_in("/w/app", since)
        };
        let none = newest_session_in("/w/app", SystemTime::now() + Duration::from_secs(60));
        unsafe { std::env::remove_var("CODEX_HOME") };
        let _ = std::fs::remove_dir_all(&home);
        assert_eq!(found.as_deref(), Some(newer));
        assert_eq!(none, None);
    }
}
