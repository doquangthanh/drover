"""`dr server run` -> the Rust daemon when the release ships one; the Python daemon otherwise.

Linux bundle: `drover-server` next to `dr` (exec). Windows: drover.exe hands over to this version's runtime
`dr.exe` (Rust, built with the daemon), installed by the Python daemon on the first start of a version. A Rust
daemon that exits during start-up falls back to the Python daemon, so Drover always has one.
`DROVER_ENGINE=python` keeps the Python daemon.
"""

from __future__ import annotations

import logging
import os
import sys
import time

log = logging.getLogger(__name__)
START_GRACE_S = 5.0  # a Rust daemon still running (or serving) after this counts as started


def bundled_rust_daemon() -> str | None:
    from drover.self_command import bundle_dir, is_frozen, is_single_exe

    if not is_frozen() or os.environ.get("DROVER_ENGINE") == "python":
        return None
    if sys.platform == "win32":
        if not is_single_exe():
            return None  # dr-py.exe asked explicitly: Python
        from drover.core.windows_cli_runtime_installer import runtime_dr_exe

        exe = runtime_dr_exe()
        return str(exe) if exe else None
    exe = bundle_dir() / "drover-server"
    return str(exe) if exe.is_file() and os.access(exe, os.X_OK) else None


def hand_over(exe: str, listen: str, background: bool) -> int | None:
    """Run the Rust daemon. Returns the exit code to use, or None when the caller should run the Python daemon."""
    argv = [exe, "server", "run", "--listen", listen] + (["--background"] if background else [])
    if sys.platform != "win32":
        os.execv(exe, argv)  # replaces this process
    import subprocess

    if not background:
        return subprocess.call(argv)
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=flags, close_fds=True)
    except OSError as exc:
        log.warning("Rust daemon %s did not start (%s); using the Python daemon", exe, exc)
        return None
    if _started(proc):
        return 0
    log.warning("Rust daemon %s exited with %s during start-up; using the Python daemon", exe, proc.returncode)
    return None


def _started(proc) -> bool:
    """True once the child answers /health under its own pid, or is still alive after the grace period."""
    from drover.daemon.daemon_client import is_alive, read_info

    deadline = time.monotonic() + START_GRACE_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        info = read_info()
        if info and info.get("pid") == proc.pid and is_alive(info):
            return True
        time.sleep(0.1)
    return proc.poll() is None
