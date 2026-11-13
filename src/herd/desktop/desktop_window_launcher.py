"""`herd` / `hd app`: native window around the daemon's web UI.

Closing the window never stops agents — they live in the daemon.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time

from herd.daemon.daemon_client import DaemonUnavailable, ensure_daemon, is_alive, read_info, ui_url


class DesktopBridge:
    """Exposed to the page as `window.pywebview.api` — only harmless, user-initiated actions."""

    def __init__(self) -> None:
        self._window = None

    def pick_folder(self, start: str = "") -> str | None:
        import webview

        start_dir = start if start and os.path.isdir(start) else os.path.expanduser("~")
        result = self._window.create_file_dialog(webview.FileDialog.FOLDER, directory=start_dir)
        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else str(result)

    def open_path(self, path: str) -> bool:
        """Open a config file/folder in the system's default app."""
        from herd.app_paths import config_dir

        real = os.path.realpath(path)
        allowed = os.path.realpath(str(config_dir()))
        if not (real == allowed or real.startswith(allowed + os.sep)):
            return False
        if sys.platform == "win32":
            os.startfile(real)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", real])
        else:
            subprocess.Popen(["xdg-open", real])
        return True

    def platform(self) -> str:
        return sys.platform


def follow_daemon(window, loaded_url: str) -> None:
    """Restarting the server changes its port and token; point the open window at the new one.

    Without this the page retries the dead address forever ("reconnecting...").
    """
    while True:
        time.sleep(1.5)
        info = read_info()
        if not info:
            continue
        url = ui_url(info)
        if url != loaded_url and is_alive(info):
            loaded_url = url
            try:
                window.load_url(url)
            except Exception:  # noqa: BLE001 - pywebview raises assorted errors while the window closes
                return


def main() -> None:
    try:
        info = ensure_daemon()
    except DaemonUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(10)
    url = ui_url(info)
    try:
        import webview
    except ImportError:
        import webbrowser

        webbrowser.open(url)
        return
    bridge = DesktopBridge()
    bridge._window = webview.create_window(
        "herd", url, js_api=bridge, width=1440, height=900, min_size=(900, 560), background_color="#131518"
    )
    from herd.app_paths import web_static_dir

    icon = web_static_dir() / ("app-icon.ico" if sys.platform == "win32" else "favicon.png")  # WinForms needs .ico
    webview.start(follow_daemon, (bridge._window, url), private_mode=False, icon=str(icon) if icon.exists() else None)


if __name__ == "__main__":
    main()
