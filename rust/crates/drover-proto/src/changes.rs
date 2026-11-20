//! Changes view data shared by native clients (port of `frontend/src/changes/use-changes-data.ts` and
//! `diff-parse.ts`): the repo's worktrees, files changed vs a base, and a unified diff as numbered rows.

use serde::Deserialize;

#[derive(Debug, Clone, Default, Deserialize, PartialEq)]
#[serde(default)]
pub struct GitInfo {
    pub is_repo: bool,
    pub root: String,
}

#[derive(Debug, Clone, Default, Deserialize, PartialEq)]
#[serde(default)]
pub struct Worktree {
    pub path: String,
    pub branch: Option<String>,
    pub changes: Option<i64>,
    /// Its folder was deleted: it cannot be opened, `worktree.prune` forgets it.
    pub missing: bool,
}

#[derive(Debug, Clone, Default, Deserialize, PartialEq)]
#[serde(default)]
pub struct ChangedFile {
    pub path: String,
    pub status: Option<String>,
    pub added: i64,
    pub removed: i64,
}

/// The base to compare against: the one typed, else the main worktree's branch, else `main`.
pub fn base(typed: &str, trees: &[Worktree]) -> String {
    let typed = typed.trim();
    if !typed.is_empty() {
        return typed.to_string();
    }
    trees.first().and_then(|t| t.branch.clone()).unwrap_or_else(|| "main".into())
}

/// The worktree to show: the picked one while it still exists, else the first task worktree, else the main one.
pub fn shown_path(picked: Option<&str>, trees: &[Worktree]) -> Option<String> {
    let live: Vec<&Worktree> = trees.iter().filter(|t| !t.missing).collect();
    if let Some(p) = picked.filter(|p| live.iter().any(|t| t.path == *p)) {
        return Some(p.to_string());
    }
    live.get(1).or(live.first()).map(|t| t.path.clone()).or_else(|| trees.first().map(|t| t.path.clone()))
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RowKind {
    Hunk,
    Added,
    Removed,
    Context,
}

/// One diff line: the hunk header has no number; removed lines carry old-file numbers, others new-file ones.
#[derive(Debug, Clone, PartialEq)]
pub struct DiffRow {
    pub kind: RowKind,
    pub text: String,
    pub n: Option<u32>,
}

fn hunk_start(line: &str) -> Option<(u32, u32)> {
    let rest = line.strip_prefix("@@ -")?;
    let (old, rest) = rest.split_once(' ')?;
    let new = rest.strip_prefix('+')?.split([' ', ',']).next()?;
    Some((old.split(',').next()?.parse().ok()?, new.parse().ok()?))
}

/// Unified diff text -> rows; empty when there is nothing to show (no text, or file headers only).
pub fn parse_diff(text: &str) -> Vec<DiffRow> {
    let header = |l: &str| ["diff --git", "index ", "--- ", "+++ "].iter().any(|h| l.starts_with(h));
    let lines: Vec<&str> = text.split('\n').filter(|l| !header(l)).collect();
    if lines.concat().trim().is_empty() {
        return vec![];
    }
    let (mut old_n, mut new_n) = (0u32, 0u32);
    lines.into_iter().map(|l| {
        if let Some((o, n)) = hunk_start(l) {
            (old_n, new_n) = (o, n);
            return DiffRow { kind: RowKind::Hunk, text: l.to_string(), n: None };
        }
        let kind = match l.as_bytes().first() {
            Some(b'+') => RowKind::Added,
            Some(b'-') => RowKind::Removed,
            _ => RowKind::Context,
        };
        let n = match kind {
            RowKind::Removed => { old_n += 1; old_n - 1 }
            RowKind::Added => { new_n += 1; new_n - 1 }
            _ => { old_n += 1; new_n += 1; new_n - 1 }
        };
        DiffRow { kind, text: format!(" {}", if l.is_empty() { " " } else { l }), n: Some(n) }
    }).collect()
}

/// "src/a/b.rs" -> ("b.rs", "src/a/").
pub fn split_path(path: &str) -> (&str, &str) {
    match path.rfind('/') {
        Some(i) => (&path[i + 1..], &path[..=i]),
        None => (path, ""),
    }
}
