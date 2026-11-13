"""In-app folder picker backend: list sub-folders, but only inside allowed roots."""

from __future__ import annotations

import os
from pathlib import Path


class FolderAccessError(Exception):
    pass


def allowed_roots(configured: list[str]) -> list[Path]:
    roots = [Path(r).expanduser() for r in configured if r] or [Path.home()]
    return [r.resolve() for r in roots if r.exists()]


def _inside(path: Path, roots: list[Path]) -> bool:
    for root in roots:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def list_dirs(path: str, configured_roots: list[str], show_hidden: bool = False) -> dict:
    roots = allowed_roots(configured_roots)
    if not roots:
        raise FolderAccessError("none of the folders in settings fs_roots exist")
    target = Path(path).expanduser().resolve() if path else roots[0]
    if not _inside(target, roots):
        raise FolderAccessError(f"{target} is outside the folders herd may browse (settings: fs_roots)")
    if not target.is_dir():
        raise FolderAccessError(f"not a folder: {target}")
    entries = []
    try:
        with os.scandir(target) as it:
            for entry in it:
                if not entry.is_dir(follow_symlinks=False):
                    continue
                hidden = entry.name.startswith(".")
                if hidden and not show_hidden:
                    continue
                try:
                    mtime = entry.stat().st_mtime
                except OSError:
                    mtime = 0
                entries.append({
                    "name": entry.name,
                    "path": entry.path,
                    "is_git": os.path.isdir(os.path.join(entry.path, ".git"))
                    or os.path.isfile(os.path.join(entry.path, ".git")),
                    "mtime": mtime,
                    "hidden": hidden,
                })
    except PermissionError as exc:
        raise FolderAccessError(f"no permission to read {target}") from exc
    entries.sort(key=lambda e: e["name"].lower())
    parent = target.parent if _inside(target.parent, roots) and target.parent != target else None
    return {
        "path": str(target),
        "parent": str(parent) if parent else None,
        "roots": [str(r) for r in roots],
        "entries": entries[:1000],
    }


def make_dir(parent: str, name: str, configured_roots: list[str]) -> str:
    if not name or any(ch in name for ch in '\\/:*?"<>|') or name in (".", ".."):
        raise FolderAccessError("invalid folder name")
    base = Path(list_dirs(parent, configured_roots)["path"])
    target = base / name
    target.mkdir(exist_ok=False)
    return str(target)
