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


def dark_title_bar(window) -> None:
    """The default title bar is bright white on top of the dark UI. Windows 10 1809+/11: dark caption, Windows 11: UI colours."""
    if sys.platform != "win32":
        return
    import ctypes

    hwnd = ctypes.windll.user32.FindWindowW(None, window.title)
    if not hwnd:
        return
    dwm = ctypes.windll.dwmapi

    def set_attr(attr: int, value: int) -> None:
        v = ctypes.c_int(value)
        dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))  # unsupported attrs just fail

    set_attr(20, 1)            # DWMWA_USE_IMMERSIVE_DARK_MODE
    set_attr(35, 0x181513)     # DWMWA_CAPTION_COLOR  (COLORREF 0x00BBGGRR of #131518)
    set_attr(34, 0x181513)     # DWMWA_BORDER_COLOR
    set_attr(36, 0xE8E6E4)     # DWMWA_TEXT_COLOR


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
    if sys.platform == "win32":
        import ctypes

        # Own taskbar identity: without it Windows can show a blank-page icon for the window's taskbar button.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Herd.Desktop")
    bridge = DesktopBridge()
    bridge._window = webview.create_window(
        " ", url, js_api=bridge, width=1440, height=900, min_size=(360, 480), background_color="#131518"
    )
    from herd.app_paths import web_static_dir

    icon = web_static_dir() / ("app-icon.ico" if sys.platform == "win32" else "favicon.png")  # WinForms needs .ico
    bridge._window.events.shown += lambda: dark_title_bar(bridge._window)
    try:
        webview.start(follow_daemon, (bridge._window, url), private_mode=False, icon=str(icon) if icon.exists() else None)
    except Exception as exc:  # noqa: BLE001 - e.g. Linux without GTK/WebKit: the web UI still works in a browser
        import webbrowser

        print(f"no native window ({exc}); opening {url} in the browser", file=sys.stderr)
        webbrowser.open(url)


if __name__ == "__main__":
    main()
