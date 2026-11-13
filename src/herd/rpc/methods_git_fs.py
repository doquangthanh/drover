"""RPC methods for the folder picker and git worktrees / Changes view."""

from __future__ import annotations

import shutil

from herd.core.folder_browser import FolderAccessError, list_dirs, make_dir
from herd.git import worktree_service as wt
from herd.rpc.rpc_registry import E_BAD_PARAMS, E_GENERAL, RpcError, need, registry


def _roots(ctx) -> list[str]:
    return list(ctx.settings.get("fs_roots", []) or [])


@registry.method("fs.list_dirs", "List sub-folders (in-app folder picker)", "path?, hidden?")
async def fs_list_dirs(ctx, p: dict) -> dict:
    try:
        return list_dirs(str(p.get("path") or ""), _roots(ctx), bool(p.get("hidden")))
    except FolderAccessError as exc:
        raise RpcError(E_BAD_PARAMS, str(exc)) from exc


@registry.method("fs.mkdir", "Create a folder inside an allowed root", "parent, name")
async def fs_mkdir(ctx, p: dict) -> dict:
    try:
        return {"path": make_dir(need(p, "parent"), need(p, "name"), _roots(ctx))}
    except (FolderAccessError, FileExistsError) as exc:
        raise RpcError(E_BAD_PARAMS, str(exc)) from exc


async def _git_call(coro):
    try:
        return await coro
    except wt.GitError as exc:
        raise RpcError(E_GENERAL, str(exc)) from exc
    except FileNotFoundError as exc:
        raise RpcError(E_GENERAL, "git is not installed or the folder is missing") from exc


@registry.method("git.info", "Is this folder a git repo, which branch, how dirty", "path")
async def git_info(ctx, p: dict) -> dict:
    return await wt.repo_info(need(p, "path"))


@registry.method("worktree.list", "Worktrees of a repo with change counts", "repo")
async def worktree_list(ctx, p: dict) -> list:
    return await _git_call(wt.list_worktrees(need(p, "repo")))


@registry.method("worktree.create", "New branch hd/<task> in <repo>-wt/<task>", "repo, task, base?")
async def worktree_create(ctx, p: dict) -> dict:
    return await _git_call(wt.create_worktree(need(p, "repo"), need(p, "task"), p.get("base", "")))


@registry.method("worktree.remove", "Remove a worktree (refuses when dirty unless force)", "path, force?")
async def worktree_remove(ctx, p: dict) -> None:
    await _git_call(wt.remove_worktree(need(p, "path"), bool(p.get("force"))))


@registry.method("worktree.changes", "Files changed vs base (committed + working tree)", "path, base")
async def worktree_changes(ctx, p: dict) -> list:
    return await _git_call(wt.changed_files(need(p, "path"), need(p, "base")))


@registry.method("worktree.diff", "Unified diff of one file vs base", "path, base, file")
async def worktree_diff(ctx, p: dict) -> dict:
    return {"diff": await _git_call(wt.file_diff(need(p, "path"), need(p, "base"), need(p, "file")))}


@registry.method("git.commit", "Stage everything and commit", "path, message")
async def git_commit(ctx, p: dict) -> dict:
    path, message = need(p, "path"), need(p, "message")
    await _git_call(wt.git(path, "add", "-A"))
    out = await _git_call(wt.git(path, "commit", "-m", message))
    return {"output": out.strip()}


@registry.method("git.push", "Push the current branch (sets upstream)", "path")
async def git_push(ctx, p: dict) -> dict:
    path = need(p, "path")
    branch = (await _git_call(wt.git(path, "rev-parse", "--abbrev-ref", "HEAD"))).strip()
    out = await _git_call(wt.git(path, "push", "-u", "origin", branch))
    return {"output": out.strip(), "branch": branch}


@registry.method("git.rebase", "Rebase the current branch onto base", "path, base")
async def git_rebase(ctx, p: dict) -> dict:
    out = await _git_call(wt.git(need(p, "path"), "rebase", need(p, "base")))
    return {"output": out.strip()}


@registry.method("git.pr", "Open a pull request with gh (if installed)", "path")
async def git_pr(ctx, p: dict) -> dict:
    if not shutil.which("gh"):
        raise RpcError(E_GENERAL, "GitHub CLI (gh) is not installed")
    import asyncio

    proc = await asyncio.create_subprocess_exec(
        "gh", "pr", "create", "--fill", cwd=need(p, "path"),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    out, _ = await proc.communicate()
    text = out.decode("utf-8", "replace").strip()
    if proc.returncode != 0:
        raise RpcError(E_GENERAL, text or "gh pr create failed")
    return {"output": text}
