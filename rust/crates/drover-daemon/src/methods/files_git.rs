//! RPC methods for the Files view, the folder picker and git worktrees / Changes view.
//! Port of `methods_files.py` and `methods_git_fs.py`.

use std::sync::Arc;

use serde_json::{Value, json};

use crate::ctx::Ctx;
use crate::fs_access;
use crate::git;
use crate::method;
use crate::rpc::{E_BAD_PARAMS, E_GENERAL, E_NOT_FOUND, MethodSpec, RpcError, RpcResult, need_str, opt_str, truthy};

pub fn methods() -> Vec<MethodSpec> {
    vec![
        method!("files.list", "List a folder inside a space or a pane's folder (folders first)", "space | pane, path?", files_list),
        method!("files.read", "Read a text file inside a space or a pane's folder (1 MB max)", "space | pane, path", files_read),
        method!("files.write", "Save a text file inside a space (create=true makes a new one)", "space, path, text, base_mtime_us?, create?, force?", files_write),
        method!("files.status", "Changed files in the git repo of a space or a pane's folder (M/A/D/R/?)", "space | pane", files_status),
        method!("fs.list_dirs", "List sub-folders (in-app folder picker)", "path?, hidden?", fs_list_dirs),
        method!("fs.mkdir", "Create a folder inside an allowed root", "parent, name", fs_mkdir),
        method!("git.info", "Is this folder a git repo, which branch, how dirty", "path", git_info),
        method!("worktree.list", "Worktrees of a repo with change counts", "repo", worktree_list),
        method!("worktree.create", "New branch dr/<task> in <repo>-wt/<task>", "repo, task, base?", worktree_create),
        method!("worktree.remove", "Remove a worktree (refuses when dirty unless force)", "path, force?", worktree_remove),
        method!("worktree.prune", "Forget worktrees whose folder no longer exists", "repo", worktree_prune),
        method!("worktree.changes", "Files changed vs base (committed + working tree)", "path, base", worktree_changes),
        method!("worktree.diff", "Unified diff of one file vs base", "path, base, file", worktree_diff),
        method!("git.commit", "Stage everything and commit", "path, message", git_commit),
        method!("git.push", "Push the current branch (sets upstream)", "path", git_push),
        method!("git.rebase", "Rebase the current branch onto base", "path, base", git_rebase),
        method!("git.pr", "Open a pull request with gh (if installed)", "path", git_pr),
    ]
}

/// The folder `files.*` work in: a pane's when `pane` is given (it follows the folder its program is in, e.g. an
/// agent's worktree outside the space; the native window's Files panel follows the focused agent), else a space's.
fn space_root(ctx: &Ctx, p: &Value) -> Result<String, RpcError> {
    if let Some(pane) = p.get("pane").and_then(Value::as_str).filter(|s| !s.is_empty()) {
        let session = ctx.manager.lock().unwrap().get(pane)?;
        return Ok(session.meta.lock().unwrap().cwd.clone());
    }
    let id = need_str(p, "space")?;
    ctx.manager.lock().unwrap().spaces.get(&id).map(|s| s.cwd.clone()).ok_or_else(|| RpcError::new(E_NOT_FOUND, "no such space"))
}

fn files_err(e: String) -> RpcError {
    RpcError::new(E_BAD_PARAMS, e)
}

fn git_err(e: String) -> RpcError {
    RpcError::new(E_GENERAL, e)
}

async fn blocking<F: FnOnce() -> Result<Value, String> + Send + 'static>(f: F) -> RpcResult {
    tokio::task::spawn_blocking(f).await.map_err(|e| git_err(e.to_string()))?.map_err(files_err)
}

async fn files_list(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let (root, rel) = (space_root(&ctx, &p)?, opt_str(&p, "path"));
    blocking(move || fs_access::list_dir(&root, &rel)).await
}

async fn files_read(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let (root, rel) = (space_root(&ctx, &p)?, need_str(&p, "path")?);
    blocking(move || fs_access::read_text(&root, &rel)).await
}

async fn files_write(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let Some(text) = p.get("text").and_then(Value::as_str).map(String::from) else {
        return Err(files_err("text must be a string".into()));
    };
    let (root, rel) = (space_root(&ctx, &p)?, need_str(&p, "path")?);
    let base = p.get("base_mtime_us").filter(|v| !v.is_null()).map(|v| v.as_i64().or_else(|| v.as_f64().map(|f| f as i64)).unwrap_or(0));
    let (create, force) = (truthy(&p, "create"), truthy(&p, "force"));
    blocking(move || fs_access::write_text(&root, &rel, &text, base, create, force)).await
}

async fn files_status(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    Ok(git::status_map(&space_root(&ctx, &p)?).await)
}

fn fs_roots(ctx: &Ctx) -> Vec<String> {
    ctx.settings.lock().unwrap().get("fs_roots").and_then(Value::as_array)
        .map(|a| a.iter().filter_map(|r| r.as_str().map(String::from)).collect()).unwrap_or_default()
}

async fn fs_list_dirs(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let (roots, path, hidden) = (fs_roots(&ctx), opt_str(&p, "path"), truthy(&p, "hidden"));
    blocking(move || fs_access::list_dirs(&path, &roots, hidden)).await
}

async fn fs_mkdir(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let (roots, parent, name) = (fs_roots(&ctx), need_str(&p, "parent")?, need_str(&p, "name")?);
    blocking(move || fs_access::make_dir(&parent, &name, &roots).map(|path| json!({"path": path}))).await
}

async fn git_info(_ctx: Arc<Ctx>, p: Value) -> RpcResult {
    Ok(git::repo_info(&need_str(&p, "path")?).await)
}

async fn worktree_list(_ctx: Arc<Ctx>, p: Value) -> RpcResult {
    git::list_worktrees(&need_str(&p, "repo")?).await.map_err(git_err)
}

async fn worktree_create(_ctx: Arc<Ctx>, p: Value) -> RpcResult {
    git::create_worktree(&need_str(&p, "repo")?, &need_str(&p, "task")?, &opt_str(&p, "base")).await.map_err(git_err)
}

async fn worktree_remove(_ctx: Arc<Ctx>, p: Value) -> RpcResult {
    git::remove_worktree(&need_str(&p, "path")?, truthy(&p, "force")).await.map_err(git_err)?;
    Ok(Value::Null)
}

async fn worktree_prune(_ctx: Arc<Ctx>, p: Value) -> RpcResult {
    git::git(&need_str(&p, "repo")?, &["worktree", "prune"], true).await.map_err(git_err)?;
    Ok(Value::Null)
}

async fn worktree_changes(_ctx: Arc<Ctx>, p: Value) -> RpcResult {
    Ok(git::changed_files(&need_str(&p, "path")?, &need_str(&p, "base")?).await)
}

async fn worktree_diff(_ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let diff = git::file_diff(&need_str(&p, "path")?, &need_str(&p, "base")?, &need_str(&p, "file")?).await;
    Ok(json!({"diff": diff}))
}

async fn git_commit(_ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let (path, message) = (need_str(&p, "path")?, need_str(&p, "message")?);
    git::git(&path, &["add", "-A"], true).await.map_err(git_err)?;
    let out = git::git(&path, &["commit", "-m", &message], true).await.map_err(git_err)?;
    Ok(json!({"output": out.trim()}))
}

async fn git_push(_ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let path = need_str(&p, "path")?;
    let branch = git::git(&path, &["rev-parse", "--abbrev-ref", "HEAD"], true).await.map_err(git_err)?.trim().to_string();
    let out = git::git(&path, &["push", "-u", "origin", &branch], true).await.map_err(git_err)?;
    Ok(json!({"output": out.trim(), "branch": branch}))
}

async fn git_rebase(_ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let out = git::git(&need_str(&p, "path")?, &["rebase", &need_str(&p, "base")?], true).await.map_err(git_err)?;
    Ok(json!({"output": out.trim()}))
}

async fn git_pr(_ctx: Arc<Ctx>, p: Value) -> RpcResult {
    if crate::launch::which("gh").is_none() {
        return Err(git_err("GitHub CLI (gh) is not installed".into()));
    }
    let out = tokio::process::Command::new("gh").args(["pr", "create", "--fill"]).current_dir(need_str(&p, "path")?)
        .stdin(std::process::Stdio::null()).output().await.map_err(|e| git_err(e.to_string()))?;
    let text = format!("{}{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr)).trim().to_string();
    if !out.status.success() {
        return Err(git_err(if text.is_empty() { "gh pr create failed".into() } else { text }));
    }
    Ok(json!({"output": text}))
}

/// Keeps each space's git branch / change count fresh so the UI can show it. Port of `git_watcher.py`.
pub async fn git_watcher(ctx: Arc<Ctx>) {
    loop {
        let spaces: Vec<(String, String)> = ctx.manager.lock().unwrap().spaces.values().map(|s| (s.id.clone(), s.cwd.clone())).collect();
        let mut fresh = std::collections::HashMap::new();
        for (id, cwd) in spaces {
            if let Some(status) = git::quick_status(&cwd).await {
                fresh.insert(id, status);
            }
        }
        {
            let mut m = ctx.manager.lock().unwrap();
            if fresh != m.git {
                m.git = fresh;
                m.changed();
            }
        }
        tokio::time::sleep(std::time::Duration::from_secs(5)).await;
    }
}
