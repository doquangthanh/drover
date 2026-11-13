"""Git helpers: repo info, task worktrees, and diffs for the Changes view."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path


class GitError(Exception):
    pass


async def git(cwd: str, *args: str, check: bool = True) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git", *args, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    if check and proc.returncode != 0:
        raise GitError(err.decode("utf-8", "replace").strip() or f"git {args[0]} failed")
    return out.decode("utf-8", "replace")


def safe_task_name(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip()).strip("-.").lower()
    if not slug:
        raise GitError("task name is empty")
    return slug[:60]


async def repo_info(path: str) -> dict:
    """Return {"is_repo", "root", "branch", "dirty"} without raising for non-repos."""
    try:
        root = (await git(path, "rev-parse", "--show-toplevel")).strip()
    except (GitError, FileNotFoundError, NotADirectoryError):
        return {"is_repo": False}
    branch = (await git(root, "rev-parse", "--abbrev-ref", "HEAD", check=False)).strip()
    status = await git(root, "status", "--porcelain", check=False)
    ahead = (await git(root, "rev-list", "--count", "@{u}..HEAD", check=False)).strip()
    return {"is_repo": True, "root": root, "branch": branch,
            "dirty": len([line for line in status.splitlines() if line.strip()]),
            "ahead": int(ahead) if ahead.isdigit() else 0}


async def list_worktrees(repo: str) -> list[dict]:
    out = await git(repo, "worktree", "list", "--porcelain")
    items, current = [], {}
    for line in out.splitlines() + [""]:
        if not line.strip():
            if current:
                items.append(current)
            current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree":
            current["path"] = value
        elif key == "branch":
            current["branch"] = value.removeprefix("refs/heads/")
        elif key in ("detached", "bare", "locked", "prunable"):
            current[key] = True
    for item in items:
        status = await git(item["path"], "status", "--porcelain", check=False)
        item["changes"] = len([line for line in status.splitlines() if line.strip()])
    return items


async def create_worktree(repo: str, task: str, base: str = "") -> dict:
    slug = safe_task_name(task)
    root = Path((await git(repo, "rev-parse", "--show-toplevel")).strip())
    base = base or (await git(str(root), "rev-parse", "--abbrev-ref", "HEAD")).strip()
    target = root.parent / f"{root.name}-wt" / slug
    if target.exists():
        raise GitError(f"{target} already exists")
    branch = f"hd/{slug}"
    await git(str(root), "worktree", "add", "-b", branch, str(target), base)
    return {"path": str(target), "branch": branch, "base": base}


async def remove_worktree(path: str, force: bool = False) -> None:
    status = await git(path, "status", "--porcelain", check=False)
    if status.strip() and not force:
        count = len(status.strip().splitlines())
        raise GitError(f"{count} uncommitted files — commit, stash or use force")
    common = (await git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")).strip()
    main_root = str(Path(common).parent)
    if Path(main_root).resolve() == Path(path).resolve():
        raise GitError("refusing to remove the main working tree")
    await git(main_root, "worktree", "remove", *(["--force"] if force else []), path)


async def changed_files(path: str, base: str) -> list[dict]:
    out = await git(path, "diff", "--numstat", f"{base}...HEAD", check=False)
    out += await git(path, "diff", "--numstat", "HEAD", check=False)
    files: dict[str, dict] = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            add, rem, name = parts
            entry = files.setdefault(name, {"path": name, "added": 0, "removed": 0})
            entry["added"] += int(add) if add.isdigit() else 0
            entry["removed"] += int(rem) if rem.isdigit() else 0
    return list(files.values())


async def file_diff(path: str, base: str, file: str) -> str:
    committed = await git(path, "diff", f"{base}...HEAD", "--", file, check=False)
    working = await git(path, "diff", "HEAD", "--", file, check=False)
    return (committed + working)[:400_000]
