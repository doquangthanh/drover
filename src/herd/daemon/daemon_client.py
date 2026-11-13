"""Find, start and call the local daemon (used by the CLI and the desktop window)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from herd.app_paths import daemon_info_file, log_dir


class DaemonUnavailable(Exception):
    pass


class RpcFailure(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def read_info() -> dict | None:
    try:
        return json.loads(daemon_info_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def is_alive(info: dict | None) -> bool:
    if not info:
        return False
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{info['port']}/health", timeout=1.5) as resp:
            return json.loads(resp.read()).get("app") == "herd"
    except (OSError, ValueError, KeyError):
        return False


def _python_for_background() -> str:
    exe = Path(sys.executable)
    if sys.platform == "win32":
        candidate = exe.with_name("pythonw.exe")
        if candidate.exists():
            return str(candidate)
    return str(exe)


def start_background() -> None:
    cmd = [_python_for_background(), "-m", "herd", "server", "run", "--background"]
    log = open(log_dir() / "daemon-stdout.log", "ab")  # noqa: SIM115 - handed to the child
    kwargs: dict = {"stdout": log, "stderr": log, "stdin": subprocess.DEVNULL, "close_fds": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                                   | subprocess.CREATE_NO_WINDOW)
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


def _claim_start_lock() -> bool:
    """Only one client launches the daemon; others just wait for it. Stale locks expire after 20s."""
    lock = daemon_info_file().with_name("starting.lock")
    try:
        if lock.exists() and time.time() - lock.stat().st_mtime > 20:
            lock.unlink()
        fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        os.close(fd)
        return True
    except FileExistsError:
        return False
    except OSError:
        return True


def ensure_daemon(timeout: float = 15) -> dict:
    info = read_info()
    if is_alive(info):
        return info
    lock = daemon_info_file().with_name("starting.lock")
    claimed = _claim_start_lock()
    if claimed:
        start_background()
    try:
        return _wait_for_daemon(timeout)
    finally:
        if claimed:
            try:
                lock.unlink()
            except OSError:
                pass


def _wait_for_daemon(timeout: float) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.25)
        info = read_info()
        if is_alive(info):
            return info
    raise DaemonUnavailable(f"herd daemon did not start; see {log_dir() / 'daemon.log'}")


def call(method: str, params: dict | None = None, timeout: float = 30, autostart: bool = True) -> object:
    info = ensure_daemon() if autostart else read_info()
    if not is_alive(info):
        raise DaemonUnavailable("herd daemon is not running (start it with `hd server start`)")
    params = dict(params or {})
    caller = os.environ.get("HD_PANE_ID")
    if caller and "caller" not in params:
        params["caller"] = caller
    body = json.dumps({"method": method, "params": params}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{info['port']}/rpc", data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {info['token']}"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            reply = json.loads(resp.read())
    except urllib.error.URLError as exc:
        raise DaemonUnavailable(f"cannot reach herd daemon: {exc}") from exc
    if "error" in reply:
        raise RpcFailure(int(reply["error"].get("code", 1)), reply["error"].get("message", "error"))
    return reply.get("result")


def ui_url(info: dict) -> str:
    return f"http://127.0.0.1:{info['port']}/?token={info['token']}"
