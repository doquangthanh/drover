"""Check GitHub for a newer herd release and swap the installed Linux bundle in place."""

from __future__ import annotations

import json
import platform
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from herd import __version__
from herd.self_command import bundle_dir, is_frozen

REPO = "doquangthanh/herd"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_URL = f"https://github.com/{REPO}/releases/download/{{tag}}/herd-linux-{{arch}}.tar.gz"
TIMEOUT = 15


class UpdateError(Exception):
    pass


def version_tuple(text: str) -> tuple[int, ...]:
    """'v0.1.5' -> (0, 1, 5); anything non-numeric is ignored."""
    return tuple(int(n) for n in re.findall(r"\d+", text.split("-")[0]))


def installable() -> bool:
    """Only the Linux release bundle can replace itself; source/uv installs update with git/uv."""
    return is_frozen() and sys.platform == "linux"


def arch() -> str:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x64"
    if machine in ("aarch64", "arm64"):
        return "arm64"
    raise UpdateError(f"unsupported CPU {machine}")


def check() -> dict:
    """Blocking: ask GitHub for the latest release."""
    req = urllib.request.Request(LATEST_API, headers={"Accept": "application/vnd.github+json", "User-Agent": "herd"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.load(resp)
    except (OSError, ValueError) as exc:
        raise UpdateError(f"could not reach GitHub: {exc}") from exc
    tag = str(data.get("tag_name", ""))
    return {
        "current": __version__, "latest": tag.lstrip("v"), "tag": tag, "url": data.get("html_url", ""),
        "notes": str(data.get("body") or "")[:4000],
        "available": bool(tag) and version_tuple(tag) > version_tuple(__version__),
        "installable": installable(),
    }


def apply(tag: str) -> None:
    """Blocking: download release `tag`, then replace the running bundle folder (rolls back on failure)."""
    if not installable():
        raise UpdateError("this install can't update itself; re-run the install script")
    if not re.fullmatch(r"v\d+(\.\d+)*", tag):
        raise UpdateError("bad version tag")
    target = bundle_dir()
    parent = target.parent
    tmp = Path(tempfile.mkdtemp(prefix=".herd-update-", dir=parent))  # same filesystem as target: rename is atomic
    try:
        archive = tmp / "herd.tar.gz"
        try:
            with urllib.request.urlopen(ASSET_URL.format(tag=tag, arch=arch()), timeout=TIMEOUT) as resp, \
                    open(archive, "wb") as out:
                shutil.copyfileobj(resp, out)
        except OSError as exc:
            raise UpdateError(f"download failed: {exc}") from exc
        with tarfile.open(archive) as tar:
            tar.extractall(tmp / "new", filter="data")
        fresh = tmp / "new" / "herd"
        if not (fresh / "hd").is_file():
            raise UpdateError("downloaded archive is missing herd/hd")
        old = tmp / "old"
        target.rename(old)
        try:
            fresh.rename(target)
        except OSError:
            old.rename(target)  # put the working copy back
            raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
