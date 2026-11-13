"""Pick the PTY backend for this OS and build default shell argv."""

from __future__ import annotations

import os
import shlex
import shutil
import sys

from herd.pty.pty_backend_interface import ExitCallback, OutputCallback, PtyBackend


def create_pty_backend(on_output: OutputCallback, on_exit: ExitCallback) -> PtyBackend:
    if sys.platform == "win32":
        from herd.pty.win_pty_backend import WinPtyBackend

        return WinPtyBackend(on_output, on_exit)
    from herd.pty.posix_pty_backend import PosixPtyBackend

    return PosixPtyBackend(on_output, on_exit)


def default_shell(configured: str = "") -> list[str]:
    if configured:
        return split_command(configured)
    if sys.platform == "win32":
        for name in ("pwsh.exe", "powershell.exe"):
            path = shutil.which(name)
            if path:
                return [path, "-NoLogo"]
        return [os.environ.get("COMSPEC", "cmd.exe")]
    return [os.environ.get("SHELL", "/bin/bash"), "-l"]


def split_command(command: str) -> list[str]:
    if sys.platform != "win32":
        return shlex.split(command)
    # Windows: keep backslashes literal (posix=False) but drop the quotes around each token,
    # so '"C:\\my tools\\claude.cmd" --continue' -> ['C:\\my tools\\claude.cmd', '--continue'].
    tokens = shlex.split(command, posix=False)
    return [t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'" else t for t in tokens]


def resolve_argv(argv: list[str]) -> list[str]:
    """On Windows, resolve `claude` to `claude.cmd`/`.exe` so ConPTY can start it."""
    if not argv:
        return argv
    if sys.platform == "win32":
        found = shutil.which(argv[0])
        if found:
            if found.lower().endswith((".cmd", ".bat")):
                return [os.environ.get("COMSPEC", "cmd.exe"), "/c", found, *argv[1:]]
            return [found, *argv[1:]]
    return argv
