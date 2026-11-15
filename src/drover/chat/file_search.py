"""Project file search for the `@` picker in a chat: list the files of a folder (git-aware) and rank them against a query."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

MAX_FILES = 50_000
CACHE_SECONDS = 10.0
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", "target", ".idea", ".vscode", ".drover"}

_cache: dict[str, tuple[float, list[str]]] = {}


def _git_files(root: str) -> list[str] | None:
    """Tracked plus untracked-but-not-ignored files; None when `root` is not inside a git work tree."""
    try:
        out = subprocess.run(["git", "-C", root, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                             capture_output=True, timeout=15, check=False,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p]


def _walk_files(root: str) -> list[str]:
    files: list[str] = []
    base = Path(root)
    for current, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        for name in names:
            files.append((Path(current) / name).relative_to(base).as_posix())
            if len(files) >= MAX_FILES:
                return files
    return files


def list_files(root: str, now: float | None = None) -> list[str]:
    """Relative, forward-slash paths. Cached for a few seconds so typing does not rescan the disk on every key."""
    now = time.monotonic() if now is None else now
    hit = _cache.get(root)
    if hit and now - hit[0] < CACHE_SECONDS:
        return hit[1]
    files = _git_files(root)
    files = _walk_files(root) if files is None else [f.replace("\\", "/") for f in files]
    files = [f for f in files if not any(part in SKIP_DIRS for part in f.split("/")[:-1])][:MAX_FILES]
    _cache[root] = (now, files)
    return files


def _subsequence(needle: str, hay: str) -> bool:
    it = iter(hay)
    return all(ch in it for ch in needle)


def _score(path: str, query: str) -> int | None:
    low = path.lower()
    base = low.rsplit("/", 1)[-1]
    if base == query:
        return 100
    if base.startswith(query):
        return 90
    if query in base:
        return 80
    if query in low:
        return 60
    return 40 if _subsequence(query, low) else None


def rank_files(files: list[str], query: str, limit: int = 30) -> list[str]:
    """Best matches first: exact file name, name prefix, name contains, path contains, letters in order. Shorter wins ties."""
    query = query.strip().lower().replace("\\", "/")
    if not query:
        return sorted(files, key=lambda f: (f.count("/"), f.lower()))[:limit]
    scored = [(s, f) for f in files if (s := _score(f, query)) is not None]
    scored.sort(key=lambda t: (-t[0], len(t[1]), t[1].lower()))
    return [f for _, f in scored[:limit]]
