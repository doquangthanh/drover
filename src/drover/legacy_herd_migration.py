"""One-time move from the old "herd" name: config/state folders and the sign-in autostart entry."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

OLD, NEW = "herd", "drover"


def move_legacy_dir(new_dir: Path) -> None:
    """If `new_dir` (…/drover) does not exist yet but …/herd does, move it over (copy when files are locked)."""
    if new_dir.name != NEW or new_dir.exists():
        return
    old_dir = new_dir.with_name(OLD)
    if not old_dir.is_dir():
        return
    try:
        old_dir.rename(new_dir)
    except OSError:  # Windows: a still-running old daemon holds its log files open
        shutil.copytree(old_dir, new_dir, dirs_exist_ok=True, ignore_dangling_symlinks=True,
                        copy_function=_copy_ignoring_locked)


def _copy_ignoring_locked(src: str, dst: str) -> None:
    try:
        shutil.copy2(src, dst)
    except OSError:
        pass


def _legacy_autostart_entry() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup/herd-daemon.cmd"
    return Path.home() / ".config/systemd/user/herd.service"


def migrate_autostart() -> None:
    """Swap an old herd autostart entry for a drover one, so sign-in starts the renamed daemon."""
    old = _legacy_autostart_entry()
    if not old.is_file():
        return
    if sys.platform != "win32":
        subprocess.run(["systemctl", "--user", "disable", "--now", "herd.service"], check=False, capture_output=True)
    old.unlink(missing_ok=True)
    from drover.cli.cli_autostart import set_autostart

    set_autostart(True)
