//! Git helpers: repo info, task worktrees, diffs for the Changes view. Port of `git/worktree_service.py`.

use std::path::{Path, PathBuf};
use std::process::Stdio;

use serde_json::{Value, json};

/// Run git in `cwd`. Err(message) on a failed spawn or (with `check`) a non-zero exit.
pub async fn git(cwd: &str, args: &[&str], check: bool) -> Result<String, String> {
    let mut cmd = tokio::process::Command::new("git");
    cmd.args(args).current_dir(cwd).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped());
    #[cfg(windows)]
    cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW: no console flash per call
    let out = cmd.output().await
        .map_err(|e| format!("git cannot run here (is git installed and the folder still there?): {e}"))?;
    if check && !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr).trim().to_string();
        return Err(if err.is_empty() { format!("git {} failed", args.first().unwrap_or(&"")) } else { err });
    }
    Ok(String::from_utf8_lossy(&out.stdout).into_owned())
}

pub fn safe_task_name(name: &str) -> Result<String, String> {
    let re = regex::Regex::new(r"[^A-Za-z0-9._-]+").unwrap();
    let slug = re.replace_all(name.trim(), "-").trim_matches(|c| c == '-' || c == '.').to_lowercase();
    if slug.is_empty() {
        return Err("task name is empty".into());
    }
    Ok(slug.chars().take(60).collect())
}

/// (branch, commits ahead of upstream, changed file count) from `git status --porcelain=v2 --branch`.
pub fn parse_status_v2(status: &str) -> (String, i64, i64) {
    let (mut branch, mut ahead, mut dirty) = (String::new(), 0, 0);
    for line in status.lines() {
        if let Some(b) = line.strip_prefix("# branch.head ") {
            branch = if b.trim() == "(detached)" { "HEAD".into() } else { b.trim().into() };
        } else if let Some(ab) = line.strip_prefix("# branch.ab ") {
            ahead = ab.split_whitespace().next().and_then(|a| a.strip_prefix('+')).and_then(|n| n.parse().ok()).unwrap_or(0);
        } else if !line.trim().is_empty() && !line.starts_with('#') {
            dirty += 1;
        }
    }
    (branch, ahead, dirty)
}

pub async fn repo_info(path: &str) -> Value {
    let (top, status) = tokio::join!(git(path, &["rev-parse", "--show-toplevel"], true),
        git(path, &["status", "--porcelain=v2", "--branch"], false));
    match (top, status) {
        (Ok(top), Ok(status)) => {
            let (branch, ahead, dirty) = parse_status_v2(&status);
            json!({"is_repo": true, "root": top.trim(), "branch": branch, "dirty": dirty, "ahead": ahead})
        }
        _ => json!({"is_repo": false}),
    }
}

/// {"branch", "dirty", "ahead"} in one git call, or None when the folder is not a git repo.
pub async fn quick_status(cwd: &str) -> Option<Value> {
    let out = git(cwd, &["status", "--porcelain=v2", "--branch"], true).await.ok()?;
    let (branch, ahead, dirty) = parse_status_v2(&out);
    Some(json!({"branch": branch, "dirty": dirty, "ahead": ahead}))
}

/// {"is_repo", "files": {path relative to cwd: M|A|D|R|?}}. Untracked folders appear once, with a trailing "/".
pub async fn status_map(cwd: &str) -> Value {
    let (prefix, out) = tokio::join!(git(cwd, &["rev-parse", "--show-prefix"], true), git(cwd, &["status", "--porcelain=v1", "-z"], true));
    let (Ok(prefix), Ok(out)) = (prefix, out) else { return json!({"is_repo": false, "files": {}}) };
    let prefix = prefix.trim();
    let mut files = serde_json::Map::new();
    let mut parts = out.split('\0');
    while let Some(entry) = parts.next() {
        if entry.len() < 4 {
            continue;
        }
        let (xy, path) = (&entry[..2], &entry[3..]);
        if xy.contains('R') || xy.contains('C') {
            parts.next(); // the old name follows as its own field
        }
        let Some(rel) = path.strip_prefix(prefix) else { continue };
        let letter = if xy == "??" { "?" } else if xy.contains('A') { "A" } else if xy.contains('D') { "D" } else if xy.contains('R') { "R" } else { "M" };
        files.insert(rel.to_string(), json!(letter));
    }
    json!({"is_repo": true, "files": files})
}

pub async fn list_worktrees(repo: &str) -> Result<Value, String> {
    let out = git(repo, &["worktree", "list", "--porcelain"], true).await?;
    let mut items: Vec<serde_json::Map<String, Value>> = vec![];
    let mut current = serde_json::Map::new();
    for line in out.lines().chain(std::iter::once("")) {
        if line.trim().is_empty() {
            if !current.is_empty() {
                items.push(std::mem::take(&mut current));
            }
            continue;
        }
        let (key, value) = line.split_once(' ').unwrap_or((line, ""));
        match key {
            "worktree" => { current.insert("path".into(), json!(value)); }
            "branch" => { current.insert("branch".into(), json!(value.trim_start_matches("refs/heads/"))); }
            "detached" | "bare" | "locked" | "prunable" => { current.insert(key.into(), json!(true)); }
            _ => {}
        }
    }
    // A worktree whose folder was deleted is still listed ("prunable"): shown as missing, not queried.
    for item in &mut items {
        let path = item["path"].as_str().unwrap_or("").to_string();
        let missing = !Path::new(&path).is_dir();
        item.insert("missing".into(), json!(missing));
        let changes = if missing { 0 } else {
            git(&path, &["status", "--porcelain"], false).await.map(|s| s.lines().filter(|l| !l.trim().is_empty()).count()).unwrap_or(0)
        };
        item.insert("changes".into(), json!(changes));
    }
    Ok(json!(items))
}

pub async fn create_worktree(repo: &str, task: &str, base: &str) -> Result<Value, String> {
    let slug = safe_task_name(task)?;
    let root = PathBuf::from(git(repo, &["rev-parse", "--show-toplevel"], true).await?.trim());
    let root_s = root.to_string_lossy().into_owned();
    let base = if base.is_empty() { git(&root_s, &["rev-parse", "--abbrev-ref", "HEAD"], true).await?.trim().to_string() } else { base.to_string() };
    let name = root.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
    let target = root.parent().unwrap_or(&root).join(format!("{name}-wt")).join(&slug);
    if target.exists() {
        return Err(format!("{} already exists", target.display()));
    }
    let branch = format!("dr/{slug}");
    git(&root_s, &["worktree", "add", "-b", &branch, &target.to_string_lossy(), &base], true).await?;
    Ok(json!({"path": target.to_string_lossy(), "branch": branch, "base": base}))
}

pub async fn remove_worktree(path: &str, force: bool) -> Result<(), String> {
    let status = git(path, &["status", "--porcelain"], false).await?;
    if !status.trim().is_empty() && !force {
        return Err(format!("{} uncommitted files — commit, stash or use force", status.trim().lines().count()));
    }
    let common = git(path, &["rev-parse", "--path-format=absolute", "--git-common-dir"], true).await?;
    let main_root = Path::new(common.trim()).parent().map(Path::to_path_buf).unwrap_or_default();
    if crate::fs_access::resolve(&main_root) == crate::fs_access::resolve(Path::new(path)) {
        return Err("refusing to remove the main working tree".into());
    }
    let main = main_root.to_string_lossy().into_owned();
    let mut args = vec!["worktree", "remove"];
    if force {
        args.push("--force");
    }
    args.push(path);
    git(&main, &args, true).await.map(|_| ())
}

pub async fn changed_files(path: &str, base: &str) -> Value {
    let range = format!("{base}...HEAD");
    let (a1, a2, a3) = (["diff", "--numstat", &range], ["diff", "--numstat", "HEAD"], ["diff", "--name-status", &range]);
    let (committed, working, kinds) = tokio::join!(git(path, &a1, false), git(path, &a2, false), git(path, &a3, false));
    let mut letters = std::collections::HashMap::new();
    for line in kinds.unwrap_or_default().lines() {
        let parts: Vec<&str> = line.split('\t').collect();
        if parts.len() >= 2 {
            letters.insert(parts[parts.len() - 1].to_string(), parts[0].chars().take(1).collect::<String>());
        }
    }
    let mut files: indexmap::IndexMap<String, (i64, i64)> = indexmap::IndexMap::new();
    for line in committed.unwrap_or_default().lines().chain(working.unwrap_or_default().lines()) {
        let parts: Vec<&str> = line.split('\t').collect();
        if let [add, rem, name] = parts[..] {
            let e = files.entry(name.to_string()).or_default();
            e.0 += add.parse::<i64>().unwrap_or(0);
            e.1 += rem.parse::<i64>().unwrap_or(0);
        }
    }
    json!(files.into_iter().map(|(name, (a, r))| json!({"path": name, "added": a, "removed": r,
        "status": letters.get(&name).cloned().unwrap_or_else(|| "M".into())})).collect::<Vec<_>>())
}

pub async fn file_diff(path: &str, base: &str, file: &str) -> String {
    let range = format!("{base}...HEAD");
    let (a1, a2) = (["diff", &range, "--", file], ["diff", "HEAD", "--", file]);
    let (a, b) = tokio::join!(git(path, &a1, false), git(path, &a2, false));
    let mut out = a.unwrap_or_default() + &b.unwrap_or_default();
    if out.len() > 400_000 {
        let mut cut = 400_000;
        while !out.is_char_boundary(cut) {
            cut -= 1;
        }
        out.truncate(cut);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn status_v2_parsing() {
        let s = "# branch.oid abc\n# branch.head main\n# branch.ab +2 -0\n1 .M N... 100644 100644 100644 a b f.txt\n? new.txt\n";
        assert_eq!(parse_status_v2(s), ("main".into(), 2, 2));
        assert_eq!(parse_status_v2("# branch.head (detached)\n").0, "HEAD");
        assert_eq!(safe_task_name(" Fix: login bug! ").unwrap(), "fix-login-bug");
        assert!(safe_task_name("..").is_err());
    }
}
