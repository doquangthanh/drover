"""How to re-launch drover itself: `python -m drover` from source, or `dr.exe` when packaged (PyInstaller)."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def is_single_exe() -> bool:
    """Windows release is one onefile drover.exe: it is also the CLI (`drover <cmd>`) and the daemon.

    The fast CLI runtime dr.exe (onedir, see windows_cli_runtime_installer) is frozen too, but unpacked next to
    itself (`_internal/`), while a onefile build unpacks into a temp folder elsewhere."""
    if not (is_frozen() and sys.platform == "win32"):
        return False
    meipass = getattr(sys, "_MEIPASS", None)
    return meipass is None or Path(meipass).resolve().parent != bundle_dir()


def bundle_dir() -> Path:
    """Folder holding drover.exe / dr.exe in a packaged build."""
    return Path(sys.executable).resolve().parent


def _runtime_owner_exe() -> str | None:
    """In the fast runtime dr.exe: the drover.exe that installed it (stored in its `.complete` marker)."""
    try:
        owner = (bundle_dir() / ".complete").read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return owner if owner and Path(owner).is_file() else None


def dr_command(windowless: bool = False) -> list[str]:
    """argv prefix that runs the `dr` CLI. `windowless` picks pythonw.exe on Windows (no console)."""
    if is_single_exe():
        return [sys.executable]
    if is_frozen() and sys.platform == "win32" and (owner := _runtime_owner_exe()):
        return [owner]  # fast runtime dr.exe: daemon, window and autostart belong to drover.exe
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
    """PATH for agent panes: in a packaged build put dr.exe first so agents can call `dr`.

    Single exe: the installed runtime folder comes first, so `dr` is its dr.exe (Rust fast path) without the
    `dr.cmd` hop through cmd.exe (~15 ms a call). The shims folder stays behind it for `hd` and for when an update
    removes that runtime folder while the pane still runs."""
    if not is_frozen():
        return current
    import os

    folders = [bundle_dir()]
    if is_single_exe():
        from drover.core.windows_cli_runtime_installer import runtime_dr_exe

        fast = runtime_dr_exe()
        folders = [*([fast.parent] if fast else []), _dr_shim_dir()]
    return os.pathsep.join([*map(str, folders), *([current] if current else [])])


def fast_cli_command() -> list[str]:
    """argv prefix for short-lived `dr` calls (Claude hooks): the unpacked runtime dr.exe when installed
    (~2x faster start), else `dr_command()`. Daemon/autostart keep `dr_command()` (dr.exe is a console app)."""
    if is_single_exe():
        from drover.core.windows_cli_runtime_installer import runtime_dr_exe

        fast = runtime_dr_exe()
        if fast is not None:
            return [str(fast)]
    return dr_command()


def shim_body() -> str:
    """dr.cmd text. Single exe: use this version's fast runtime dr.exe when its `.complete` marker exists, else
    drover.exe. The text depends only on the version, so it never changes while panes run it (cmd re-reads a
    batch file by byte offset). `goto` instead of an `if (...)` block so arguments containing parentheses can't
    break cmd's parsing; `exit /b %errorlevel%` keeps dr's exit code."""
    exe = sys.executable
    if not is_single_exe():
        return f'@"{exe}" %*\r\n'
    from drover.core.windows_cli_runtime_installer import DONE_MARKER, runtime_dir

    folder = runtime_dir()
    return (f'@if not exist "{folder / DONE_MARKER}" goto drover\r\n'
            f'@"{folder / "dr.exe"}" %*\r\n@exit /b %errorlevel%\r\n'
            f':drover\r\n@"{exe}" %*\r\n')


def _dr_shim_dir() -> Path:
    """Folder with `dr.cmd` (and the old `hd.cmd` name) forwarding to dr, so agent panes can call `dr`."""
    from drover.app_paths import state_dir

    shims = state_dir() / "shims"
    shims.mkdir(parents=True, exist_ok=True)
    body = shim_body().encode("utf-8")
    for name in ("dr.cmd", "hd.cmd"):
        cmd = shims / name
        if not cmd.exists() or cmd.read_bytes() != body:
            cmd.write_bytes(body)  # bytes: text mode would turn \r\n into \r\r\n and rewrite it every time
    return shims
