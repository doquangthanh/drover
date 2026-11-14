"""Where is the user's `claude`? On Windows the SDK only accepts a native claude.exe, but an npm install puts a
`claude.cmd` shim on PATH. The real program sits inside the npm package next to that shim, so we point the SDK at it."""

from __future__ import annotations

import os
import sys
from pathlib import Path

NPM_PACKAGE_EXE = Path("node_modules") / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"


def find_claude_exe(path_env: str | None = None, home: Path | None = None) -> str | None:
    """Absolute path of a native claude.exe, or None (other systems, or nothing found: the SDK then searches itself)."""
    if sys.platform != "win32":
        return None
    for entry in (path_env if path_env is not None else os.environ.get("PATH", "")).split(os.pathsep):
        directory = Path(entry)
        if not entry or not directory.is_absolute():
            continue
        if (directory / "claude.exe").is_file():
            return str(directory / "claude.exe")
        if (directory / "claude.cmd").is_file() and (directory / NPM_PACKAGE_EXE).is_file():  # npm global install
            return str(directory / NPM_PACKAGE_EXE)
    native = (home or Path.home()) / ".local" / "bin" / "claude.exe"
    return str(native) if native.is_file() else None
