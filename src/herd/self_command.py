"""How to re-launch herd itself: `python -m herd` from source, or `hd.exe` when packaged (PyInstaller)."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def bundle_dir() -> Path:
    """Folder holding herd.exe / hd.exe in a packaged build."""
    return Path(sys.executable).resolve().parent


def hd_command(windowless: bool = False) -> list[str]:
    """argv prefix that runs the `hd` CLI. `windowless` picks pythonw.exe on Windows (no console)."""
    if is_frozen():
        name = "hd.exe" if sys.platform == "win32" else "hd"
        return [str(bundle_dir() / name)]
    exe = Path(sys.executable)
    if windowless and sys.platform == "win32":
        pyw = exe.with_name("pythonw.exe")
        if pyw.exists():
            exe = pyw
    return [str(exe), "-m", "herd"]


def pane_path(current: str) -> str:
    """PATH for agent panes: in a packaged build put hd.exe first so agents can call `hd`."""
    if not is_frozen():
        return current
    import os

    return str(bundle_dir()) + os.pathsep + current if current else str(bundle_dir())
