//! Project file search for the `@` picker in a chat: list a folder's files (git-aware) and rank them against a
//! query. Port of `file_search.py`.

use std::collections::HashMap;
use std::path::Path;
use std::sync::{LazyLock, Mutex};
use std::time::{Duration, Instant};

const MAX_FILES: usize = 50_000;
const CACHE_FOR: Duration = Duration::from_secs(10);
const SKIP_DIRS: &[&str] = &[".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", "target",
                             ".idea", ".vscode", ".drover"];

static CACHE: LazyLock<Mutex<HashMap<String, (Instant, Vec<String>)>>> = LazyLock::new(Default::default);

/// Tracked plus untracked-but-not-ignored files; None when `root` is not inside a git work tree.
fn git_files(root: &str) -> Option<Vec<String>> {
    let mut cmd = std::process::Command::new("git");
    cmd.args(["-C", root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"]);
    #[cfg(windows)]
    std::os::windows::process::CommandExt::creation_flags(&mut cmd, 0x0800_0000);
    let out = cmd.output().ok().filter(|o| o.status.success())?;
    Some(String::from_utf8_lossy(&out.stdout).split('\0').filter(|p| !p.is_empty()).map(|p| p.replace('\\', "/")).collect())
}

fn walk_files(root: &Path, dir: &Path, out: &mut Vec<String>) {
    let Ok(entries) = std::fs::read_dir(dir) else { return };
    let mut entries: Vec<_> = entries.flatten().collect();
    entries.sort_by_key(|e| e.file_name());
    for entry in entries {
        if out.len() >= MAX_FILES {
            return;
        }
        let name = entry.file_name().to_string_lossy().to_string();
        let Ok(kind) = entry.file_type() else { continue };
        if kind.is_dir() {
            if !SKIP_DIRS.contains(&name.as_str()) && !name.starts_with('.') {
                walk_files(root, &entry.path(), out);
            }
        } else if let Ok(rel) = entry.path().strip_prefix(root) {
            out.push(rel.to_string_lossy().replace('\\', "/"));
        }
    }
}

/// Relative, forward-slash paths. Cached for a few seconds so typing does not rescan the disk on every key.
pub fn list_files(root: &str) -> Vec<String> {
    if let Some((at, files)) = CACHE.lock().unwrap().get(root)
        && at.elapsed() < CACHE_FOR
    {
        return files.clone();
    }
    let files = git_files(root).unwrap_or_else(|| {
        let mut out = vec![];
        walk_files(Path::new(root), Path::new(root), &mut out);
        out
    });
    let files: Vec<String> = files.into_iter()
        .filter(|f| { let parts: Vec<&str> = f.split('/').collect(); !parts[..parts.len() - 1].iter().any(|p| SKIP_DIRS.contains(p)) })
        .take(MAX_FILES)
        .collect();
    CACHE.lock().unwrap().insert(root.to_string(), (Instant::now(), files.clone()));
    files
}

fn subsequence(needle: &str, hay: &str) -> bool {
    let mut it = hay.chars();
    needle.chars().all(|c| it.by_ref().any(|h| h == c))
}

fn score(path: &str, query: &str) -> Option<i32> {
    let low = path.to_lowercase();
    let base = low.rsplit('/').next().unwrap_or(&low);
    if base == query {
        Some(100)
    } else if base.starts_with(query) {
        Some(90)
    } else if base.contains(query) {
        Some(80)
    } else if low.contains(query) {
        Some(60)
    } else {
        subsequence(query, &low).then_some(40)
    }
}

/// Best matches first: exact file name, name prefix, name contains, path contains, letters in order. Shorter wins.
pub fn rank_files(files: &[String], query: &str, limit: usize) -> Vec<String> {
    let query = query.trim().to_lowercase().replace('\\', "/");
    if query.is_empty() {
        let mut all: Vec<&String> = files.iter().collect();
        all.sort_by_key(|f| (f.matches('/').count(), f.to_lowercase()));
        return all.into_iter().take(limit).cloned().collect();
    }
    let mut scored: Vec<(i32, &String)> = files.iter().filter_map(|f| Some((score(f, &query)?, f))).collect();
    scored.sort_by_key(|(s, f)| (-s, f.chars().count(), f.to_lowercase()));
    scored.into_iter().take(limit).map(|(_, f)| f.clone()).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ranking_prefers_names_then_paths_then_letters_in_order() {
        let files: Vec<String> = ["src/pricing.tsx", "README.md", "docs/pricing-notes/x.md", "src/p_r_i_c.ts", "pric"]
            .iter().map(|s| s.to_string()).collect();
        assert_eq!(rank_files(&files, "pric", 10), ["pric", "src/pricing.tsx", "docs/pricing-notes/x.md", "src/p_r_i_c.ts"]);
        assert_eq!(rank_files(&files, "", 2), ["pric", "README.md"]);
    }

    #[test]
    fn plain_folder_is_walked_without_skipped_dirs() {
        let root = std::env::temp_dir().join(format!("drover-files-{}", crate::chat::new_id()));
        std::fs::create_dir_all(root.join("src")).unwrap();
        std::fs::create_dir_all(root.join("node_modules/x")).unwrap();
        std::fs::write(root.join("src/a.ts"), "").unwrap();
        std::fs::write(root.join("node_modules/x/b.js"), "").unwrap();
        assert_eq!(list_files(root.to_str().unwrap()), ["src/a.ts"]);
        let _ = std::fs::remove_dir_all(root);
    }
}
