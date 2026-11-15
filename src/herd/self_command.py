"""How to re-launch herd itself: `python -m herd` from source, or `hd.exe` when packaged (PyInstaller)."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_single_exe() -> bool:
    """Windows release is one onefile herd.exe: it is also the CLI (`herd <cmd>`) and the daemon."""
    return is_frozen() and sys.platform == "win32"


def bundle_dir() -> Path:
    """Folder holding herd.exe / hd.exe in a packaged build."""
    return Path(sys.executable).resolve().parent


def hd_command(windowless: bool = False) -> list[str]:
    """argv prefix that runs the `hd` CLI. `windowless` picks pythonw.exe on Windows (no console)."""
    if is_single_exe():
        return [sys.executable]
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

    folder = _hd_shim_dir() if is_single_exe() else bundle_dir()
    return str(folder) + os.pathsep + current if current else str(folder)


def _hd_shim_dir() -> Path:
    """Folder with an `hd.cmd` forwarding to herd.exe, so agent panes can still call `hd`."""
    from herd.app_paths import state_dir

    shims = state_dir() / "shims"
    shims.mkdir(parents=True, exist_ok=True)
    cmd = shims / "hd.cmd"
    body = f'@"{sys.executable}" %*\r\n'
    if not cmd.exists() or cmd.read_text(encoding="utf-8") != body:
        cmd.write_text(body, encoding="utf-8")
    return shims
