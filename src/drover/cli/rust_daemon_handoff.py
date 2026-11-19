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
START_TIMEOUT_S = 20.0  # longer than any normal start (session load, antivirus scan of a fresh dr.exe)


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
    from drover.app_paths import log_dir

    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
    # Drop the onefile launcher's _PYI_* variables: they point at its temp folder, gone once drover.exe exits, and
    # the daemon starts drover.exe again (self-update, restart) and hands its environment to every pane.
    env = {k: v for k, v in os.environ.items() if not k.startswith("_PYI_")} | {"PYINSTALLER_RESET_ENVIRONMENT": "1"}
    try:
        with open(log_dir() / "daemon-stdout.log", "ab") as log_file:  # start-up errors printed before the logger
            proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log_file, stderr=log_file, env=env,
                                    creationflags=flags, close_fds=True)
    except OSError as exc:
        log.warning("Rust daemon %s did not start (%s); using the Python daemon", exe, exc)
        return None
    if _started(proc):
        return 0
    log.warning("Rust daemon %s exited with %s during start-up; using the Python daemon", exe, proc.returncode)
    return None


def _started(proc) -> bool:
    """True once the child answers /health under its own pid; False if it exits first. Still starting after
    START_TIMEOUT_S: counted as started (it is alive; clients keep waiting for it)."""
    from drover.daemon.daemon_client import is_alive, read_info

    deadline = time.monotonic() + START_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        info = read_info()
        if info and info.get("pid") == proc.pid and is_alive(info):
            return True
        time.sleep(0.1)
    return proc.poll() is None
