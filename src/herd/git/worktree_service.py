"""Git helpers: repo info, task worktrees, and diffs for the Changes view."""

from __future__ import annotations

import asyncio
import re
import subprocess
import sys
from pathlib import Path

# The daemon runs without a console; on Windows each console child would otherwise get a fresh one (~150 ms).
NO_CONSOLE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}


class GitError(Exception):
    pass


async def git(cwd: str, *args: str, check: bool = True) -> str:
    proc = await asyncio.create_subprocess_exec(
        "git", *args, cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.DEVNULL, **NO_CONSOLE,
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
    """Return {"is_repo", "root", "branch", "dirty", "ahead"} without raising for non-repos.

    Two git processes run in parallel; `status --porcelain=v2 --branch` carries branch + ahead too.
    """
    top, status = await asyncio.gather(
        git(path, "rev-parse", "--show-toplevel"),
        git(path, "status", "--porcelain=v2", "--branch", check=False),
        return_exceptions=True,  # a missing folder fails both; collect both errors
    )
    if isinstance(top, BaseException) or isinstance(status, BaseException):
        if isinstance(top, (GitError, OSError)) or isinstance(status, OSError):
            return {"is_repo": False}
        raise top if isinstance(top, BaseException) else status
    branch, ahead, dirty = _parse_status_v2(status)
    return {"is_repo": True, "root": top.strip(), "branch": branch, "dirty": dirty, "ahead": ahead}


def _parse_status_v2(status: str) -> tuple[str, int, int]:
    """(branch, commits ahead of upstream, changed file count) from `git status --porcelain=v2 --branch`."""
    branch, ahead, dirty = "", 0, 0
    for line in status.splitlines():
        if line.startswith("# branch.head "):
            branch = line.removeprefix("# branch.head ").strip()
            branch = "HEAD" if branch == "(detached)" else branch
        elif line.startswith("# branch.ab "):
            ab = line.split()[2]  # "+N"
            ahead = int(ab[1:]) if ab[1:].isdigit() else 0
        elif line.strip() and not line.startswith("#"):
            dirty += 1
    return branch, ahead, dirty


async def quick_status(cwd: str) -> dict | None:
    """{"branch", "dirty", "ahead"} for a folder in one git call, or None when it is not a git repo."""
    try:
        branch, ahead, dirty = _parse_status_v2(await git(cwd, "status", "--porcelain=v2", "--branch"))
    except (GitError, OSError):
        return None
    return {"branch": branch, "dirty": dirty, "ahead": ahead}


async def status_map(cwd: str) -> dict:
    """{"is_repo", "files": {path relative to cwd: M|A|D|R|?}}. Untracked folders appear once, with a trailing "/"."""
    try:
        prefix, out = await asyncio.gather(
            git(cwd, "rev-parse", "--show-prefix"),
            git(cwd, "status", "--porcelain=v1", "-z"),
        )
    except (GitError, OSError):
        return {"is_repo": False, "files": {}}
    prefix = prefix.strip()
    files: dict[str, str] = {}
    parts = out.split("\0")
    i = 0
    while i < len(parts):
        entry = parts[i]
        i += 1
        if len(entry) < 4:
            continue
        xy, path = entry[:2], entry[3:]
        if "R" in xy or "C" in xy:
            i += 1  # the old name follows as its own field
        if prefix and not path.startswith(prefix):
            continue
        letter = "?" if xy == "??" else "A" if "A" in xy else "D" if "D" in xy else "R" if "R" in xy else "M"
        files[path[len(prefix):]] = letter
    return {"is_repo": True, "files": files}


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
    # A worktree whose folder was deleted is still listed (git calls it "prunable"); asking it for a status would
    # fail with WinError 267 and take the whole list down, so it is shown as missing instead.
    for item in items:
        item["missing"] = not Path(item["path"]).is_dir()
    live = [i for i in items if not i["missing"]]
    statuses = await asyncio.gather(*(git(i["path"], "status", "--porcelain", check=False) for i in live),
                                    return_exceptions=True)
    for item, status in zip(live, statuses):
        item["changes"] = 0 if isinstance(status, BaseException) else len([x for x in status.splitlines() if x.strip()])
    for item in items:
        item.setdefault("changes", 0)
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
    committed, working, kinds = await asyncio.gather(
        git(path, "diff", "--numstat", f"{base}...HEAD", check=False),
        git(path, "diff", "--numstat", "HEAD", check=False),
        git(path, "diff", "--name-status", f"{base}...HEAD", check=False),
    )
    out = committed + working
    letters = {}
    for line in kinds.splitlines():
        parts = line.split("	")
        if len(parts) >= 2:
            letters[parts[-1]] = parts[0][:1]
    files: dict[str, dict] = {}
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            add, rem, name = parts
            entry = files.setdefault(name, {"path": name, "added": 0, "removed": 0, "status": letters.get(name, "M")})
            entry["added"] += int(add) if add.isdigit() else 0
            entry["removed"] += int(rem) if rem.isdigit() else 0
    return list(files.values())


async def file_diff(path: str, base: str, file: str) -> str:
    committed, working = await asyncio.gather(
        git(path, "diff", f"{base}...HEAD", "--", file, check=False),
        git(path, "diff", "HEAD", "--", file, check=False),
    )
    return (committed + working)[:400_000]
