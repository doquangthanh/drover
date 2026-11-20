"""`dr app` / bare `dr` without Textual: open a Drover window, or the web UI in the browser.

The windows live in other repos (drover-desktop: `drover-native`, GPUI; drover-web: `drover`, Tauri, started with `app`). This repo only
starts the daemon and finds whichever window program sits next to `dr` or on PATH; with none it opens the browser.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser
from pathlib import Path

from drover.daemon.daemon_client import DaemonUnavailable, ensure_daemon, ui_url

WINDOW_PROGRAMS = ("drover-native", "drover")  # first one found wins


def find_window_program() -> str | None:
    exe_dir = Path(sys.executable).resolve().parent
    for name in WINDOW_PROGRAMS:
        for candidate in (exe_dir / name, exe_dir / f"{name}.exe"):
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        found = shutil.which(name)
        if found:
            return found
    return None


def open_app() -> int:
    try:
        info = ensure_daemon()
    except DaemonUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 10
    program = find_window_program()
    if program:
        detach = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS}
                  if sys.platform == "win32" else {"start_new_session": True})
        subprocess.Popen([program, *(["app"] if Path(program).stem == "drover" else [])], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **detach)
        return 0
    url = ui_url(info)
    print(f"no Drover window installed (drover-native or drover); opening {url} in the browser", file=sys.stderr)
    webbrowser.open(url)
    return 0
