"""How to re-launch drover itself: `python -m drover` from source, or `dr.exe` when packaged (PyInstaller)."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_single_exe() -> bool:
    """Windows release is one onefile drover.exe: it is also the CLI (`drover <cmd>`) and the daemon."""
    return is_frozen() and sys.platform == "win32"


def bundle_dir() -> Path:
    """Folder holding drover.exe / dr.exe in a packaged build."""
    return Path(sys.executable).resolve().parent


def dr_command(windowless: bool = False) -> list[str]:
    """argv prefix that runs the `dr` CLI. `windowless` picks pythonw.exe on Windows (no console)."""
    if is_single_exe():
        return [sys.executable]
    if is_frozen():
        name = "dr.exe" if sys.platform == "win32" else "dr"
        return [str(bundle_dir() / name)]
    exe = Path(sys.executable)
    if windowless and sys.platform == "win32":
        pyw = exe.with_name("pythonw.exe")
        if pyw.exists():
            exe = pyw
    return [str(exe), "-m", "drover"]


def pane_path(current: str) -> str:
    """PATH for agent panes: in a packaged build put dr.exe first so agents can call `dr`."""
    if not is_frozen():
        return current
    import os

    folder = _dr_shim_dir() if is_single_exe() else bundle_dir()
    return str(folder) + os.pathsep + current if current else str(folder)


def _dr_shim_dir() -> Path:
    """Folder with `dr.cmd` (and the old `hd.cmd` name) forwarding to drover.exe, so agent panes can call `dr`."""
    from drover.app_paths import state_dir

    shims = state_dir() / "shims"
    shims.mkdir(parents=True, exist_ok=True)
    body = f'@"{sys.executable}" %*\r\n'
    for name in ("dr.cmd", "hd.cmd"):
        cmd = shims / name
        if not cmd.exists() or cmd.read_text(encoding="utf-8") != body:
            cmd.write_text(body, encoding="utf-8")
    return shims
