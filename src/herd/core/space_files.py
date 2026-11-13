"""Read-only file access for the Files view: browse and read files, but only inside a space's folder."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

MAX_BYTES = 1_000_000  # larger files are cut here and flagged `truncated`
MAX_WRITE_BYTES = 5_000_000
MAX_ENTRIES = 3000
HIDDEN = {".git"}  # never listed: huge, and git internals are not "code"


class FileAccessError(Exception):
    pass


def resolve_inside(root: str, rel: str) -> Path:
    """`root/rel` resolved; refuses `..` and symlinks that lead outside the space."""
    base = Path(root).resolve()
    target = (base / rel).resolve() if rel else base
    try:
        target.relative_to(base)
    except ValueError:
        raise FileAccessError("path is outside this space") from None
    return target


def _rel(base: Path, path: Path) -> str:
    return path.relative_to(base).as_posix()


def list_dir(root: str, rel: str = "") -> dict:
    target = resolve_inside(root, rel)
    if not target.is_dir():
        raise FileAccessError(f"not a folder: {rel or '.'}")
    base = Path(root).resolve()
    entries = []
    try:
        with os.scandir(target) as it:
            for e in it:
                if e.name in HIDDEN:
                    continue
                is_dir = e.is_dir(follow_symlinks=False)
                try:
                    size = 0 if is_dir else e.stat().st_size
                except OSError:
                    size = 0
                entries.append({"name": e.name, "path": _rel(base, Path(e.path)), "dir": is_dir, "size": size})
    except PermissionError as exc:
        raise FileAccessError(f"no permission to read {rel or '.'}") from exc
    entries.sort(key=lambda x: (not x["dir"], x["name"].lower()))
    return {"path": rel, "entries": entries[:MAX_ENTRIES], "truncated": len(entries) > MAX_ENTRIES}


def _mtime_us(path: Path) -> int:
    return path.stat().st_mtime_ns // 1000  # microseconds: still exact when JSON turns it into a JS number


def read_text(root: str, rel: str) -> dict:
    target = resolve_inside(root, rel)
    if not target.is_file():
        raise FileAccessError(f"not a file: {rel}")
    stat = target.stat()
    with open(target, "rb") as fh:
        data = fh.read(MAX_BYTES)
    if b"\x00" in data[:8192]:
        return {"path": rel, "binary": True, "size": stat.st_size}
    truncated = stat.st_size > MAX_BYTES
    try:
        text, lossy = data.decode("utf-8"), False
    except UnicodeDecodeError:
        text, lossy = data.decode("utf-8", "replace"), True
    # Saving a cut-off or lossily decoded file would destroy data, so those open read-only.
    return {"path": rel, "binary": False, "size": stat.st_size, "truncated": truncated, "text": text,
            "lines": text.count("\n") + (0 if text.endswith("\n") or not text else 1),
            "mtime_us": _mtime_us(target), "editable": not (truncated or lossy),
            "why_readonly": "larger than 1 MB" if truncated else "not UTF-8 text" if lossy else ""}


class FileConflict(FileAccessError):
    """The file changed on disk since the editor loaded it."""


def write_text(root: str, rel: str, text: str, base_mtime_us: int | None = None, create: bool = False,
               force: bool = False) -> dict:
    """Save `text` into the space. Atomic (temp file + replace). Git internals are never writable."""
    target = resolve_inside(root, rel)
    base = Path(root).resolve()
    if not rel or ".git" in [part.lower() for part in target.relative_to(base).parts]:
        raise FileAccessError("this path cannot be written")
    data = text.encode("utf-8")
    if len(data) > MAX_WRITE_BYTES:
        raise FileAccessError("file is too large to save from the editor")
    if create:
        if target.exists():
            raise FileAccessError(f"already exists: {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
    else:
        if not target.is_file():
            raise FileAccessError(f"not a file: {rel}")
        if not force and base_mtime_us is not None and _mtime_us(target) != base_mtime_us:
            raise FileConflict("File changed on disk since you opened it (an agent may have edited it).")
    tmp = target.with_name(f".{target.name}.herd-tmp")
    try:
        tmp.write_bytes(data)
        if not create:
            shutil.copymode(target, tmp)
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return {"mtime_us": _mtime_us(target), "size": len(data)}
