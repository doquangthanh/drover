"""Check GitHub for a newer drover release and replace this install in place (Linux bundle or Windows drover.exe)."""

from __future__ import annotations

import http.client
import json
import platform
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

from drover import __version__
from drover.self_command import bundle_dir, is_frozen, is_single_exe

REPO = "doquangthanh/drover"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
LATEST_PAGE = f"https://github.com/{REPO}/releases/latest"
ASSET_URL = f"https://github.com/{REPO}/releases/download/{{tag}}/drover-linux-{{arch}}.tar.gz"
EXE_URL = f"https://github.com/{REPO}/releases/download/{{tag}}/drover.exe"
TIMEOUT = 15
MIN_EXE_BYTES = 1_000_000  # a real drover.exe is tens of MB; anything tiny is an error page


class UpdateError(Exception):
    pass


def download(url: str, dest: Path) -> None:
    """Blocking: save `url` to `dest`; UpdateError on any network/disk error (partial file removed)."""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT) as resp, open(dest, "wb") as out:
            shutil.copyfileobj(resp, out)
    except (OSError, http.client.HTTPException) as exc:  # HTTPException: e.g. IncompleteRead on a cut connection
        dest.unlink(missing_ok=True)
        raise UpdateError(f"download failed: {exc}") from exc


def version_tuple(text: str) -> tuple[int, ...]:
    """'v0.1.5' -> (0, 1, 5); anything non-numeric is ignored."""
    return tuple(int(n) for n in re.findall(r"\d+", text.split("-")[0]))


def installable() -> bool:
    """Release builds replace themselves (Linux bundle, Windows drover.exe); source/uv installs update with git/uv."""
    return is_single_exe() or (is_frozen() and sys.platform == "linux")


def arch() -> str:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x64"
    if machine in ("aarch64", "arm64"):
        return "arm64"
    raise UpdateError(f"unsupported CPU {machine}")


def check() -> dict:
    """Blocking: ask GitHub for the latest release.

    The API allows 60 unauthenticated calls an hour per IP; when it refuses, the tag is read from where
    github.com/<repo>/releases/latest redirects (no rate limit, but no release notes either).
    """
    req = urllib.request.Request(LATEST_API, headers={"Accept": "application/vnd.github+json", "User-Agent": "drover"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            data = json.load(resp)
    except (OSError, ValueError) as exc:
        data = {"tag_name": latest_tag_from_redirect(exc)}
        data["html_url"] = f"{LATEST_PAGE.rsplit('/', 1)[0]}/tag/{data['tag_name']}"
    tag = str(data.get("tag_name", ""))
    return {
        "current": __version__, "latest": tag.lstrip("v"), "tag": tag, "url": data.get("html_url", ""),
        "notes": str(data.get("body") or "")[:4000],
        "available": bool(tag) and version_tuple(tag) > version_tuple(__version__),
        "installable": installable(),
    }


def latest_tag_from_redirect(api_error: Exception) -> str:
    """Fallback for check(): the final URL of /releases/latest ends in /tag/<tag>."""
    req = urllib.request.Request(LATEST_PAGE, method="HEAD", headers={"User-Agent": "drover"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            final_url = resp.geturl()
    except OSError as exc:
        raise UpdateError(f"could not reach GitHub: {api_error}") from exc
    match = re.search(r"/tag/(v[\d.]+)$", final_url)
    if not match:
        raise UpdateError(f"could not reach GitHub: {api_error}")
    return match.group(1)


def apply(tag: str) -> None:
    """Blocking: download release `tag`, then replace the running bundle folder (rolls back on failure)."""
    if not installable():
        raise UpdateError("this install can't update itself; re-run the install script")
    if not re.fullmatch(r"v\d+(\.\d+)*", tag):
        raise UpdateError("bad version tag")
    if is_single_exe():
        apply_windows_exe(tag, Path(sys.executable).resolve())
        return
    target = bundle_dir()
    parent = target.parent
    tmp = Path(tempfile.mkdtemp(prefix=".drover-update-", dir=parent))  # same filesystem as target: rename is atomic
    try:
        archive = tmp / "drover.tar.gz"
        download(ASSET_URL.format(tag=tag, arch=arch()), archive)
        with tarfile.open(archive) as tar:
            tar.extractall(tmp / "new", filter="data")
        fresh = tmp / "new" / "drover"
        if not (fresh / "dr").is_file():
            raise UpdateError("downloaded archive is missing drover/dr")
        old = tmp / "old"
        target.rename(old)
        try:
            fresh.rename(target)
        except OSError:
            old.rename(target)  # put the working copy back
            raise
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


MAX_OLD_EXES = 20


def free_old_exe_path(exe: Path) -> Path:
    """Where to move the running exe: drover.exe.old, or drover.exe.old2, .old3... while older ones are still run
    by a window or daemon that was never restarted (Windows can't delete a running .exe)."""
    for n in range(1, MAX_OLD_EXES + 1):
        candidate = exe.with_name(exe.name + (".old" if n == 1 else f".old{n}"))
        try:
            candidate.unlink(missing_ok=True)  # left by a previous update
            return candidate
        except OSError:
            continue  # still running: try the next name
    raise UpdateError("too many older drover.exe copies are still running; restart Drover and retry")


def swap_in_exe(staged: Path, exe: Path) -> None:
    """Move the running exe aside and give the staged download its name; restores the old one on failure."""
    try:
        old = free_old_exe_path(exe)
    except UpdateError:
        staged.unlink(missing_ok=True)
        raise
    try:
        exe.rename(old)
    except OSError as exc:
        staged.unlink(missing_ok=True)
        raise UpdateError(f"could not move the running drover.exe aside: {exc}") from exc
    try:
        staged.rename(exe)
    except OSError as exc:
        old.rename(exe)  # put the working copy back
        staged.unlink(missing_ok=True)
        raise UpdateError(f"could not install the new drover.exe: {exc}") from exc


def apply_windows_exe(tag: str, exe: Path) -> None:
    """Blocking: download drover.exe for `tag` next to the running one and swap them.

    Windows refuses to overwrite or delete a running .exe but allows renaming it, so the running file becomes
    drover.exe.old (or .old2... if an older copy still runs; removed on the next start by `remove_old_exe`) and the
    download takes its name.
    """
    staged = exe.with_name(exe.name + ".new")
    download(EXE_URL.format(tag=tag), staged)
    with open(staged, "rb") as fh:
        head = fh.read(2)
    if head != b"MZ" or staged.stat().st_size < MIN_EXE_BYTES:
        staged.unlink(missing_ok=True)
        raise UpdateError("downloaded file is not a Windows program")
    swap_in_exe(staged, exe)


def remove_old_exes(exe: Path) -> None:
    """Delete every drover.exe.old* left by earlier updates that nothing runs any more (best effort)."""
    for old in exe.parent.glob(exe.name + ".old*"):
        try:
            old.unlink()
        except OSError:
            pass  # an old window or daemon still runs it; the next start retries


def remove_old_exe() -> None:
    """On start-up: clean up after the previous in-app update."""
    if is_single_exe():
        remove_old_exes(Path(sys.executable).resolve())
