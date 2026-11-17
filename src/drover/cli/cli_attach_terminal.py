"""`dr attach`: drive one pane from the current terminal over the daemon websocket.

Ctrl+\\ detaches; the agent keeps running in the daemon.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import threading

import aiohttp

from drover.daemon.daemon_client import ensure_daemon

DETACH = "\x1c"  # Ctrl+\


class RawTerminal:
    """Put the local terminal into raw mode and restore it afterwards (Windows + POSIX)."""

    def __enter__(self):
        if sys.platform == "win32":
            import ctypes

            k32 = ctypes.windll.kernel32
            self._hin, self._hout = k32.GetStdHandle(-10), k32.GetStdHandle(-11)
            self._in_mode, self._out_mode = ctypes.c_uint(), ctypes.c_uint()
            k32.GetConsoleMode(self._hin, ctypes.byref(self._in_mode))
            k32.GetConsoleMode(self._hout, ctypes.byref(self._out_mode))
            k32.SetConsoleMode(self._hin, 0x0200)  # ENABLE_VIRTUAL_TERMINAL_INPUT only (raw)
            k32.SetConsoleMode(self._hout, self._out_mode.value | 0x0004 | 0x0001)  # VT processing
        else:
            import termios
            import tty

            self._fd = sys.stdin.fileno()
            self._saved = termios.tcgetattr(self._fd)
            tty.setraw(self._fd)
        return self

    def __exit__(self, *exc):
        if sys.platform == "win32":
            import ctypes

            k32 = ctypes.windll.kernel32
            k32.SetConsoleMode(self._hin, self._in_mode.value)
            k32.SetConsoleMode(self._hout, self._out_mode.value)
        else:
            import termios

            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)
        sys.stdout.write("\x1b[?1049l\x1b[0m\r\n[detached — the agent keeps running]\r\n")
        sys.stdout.flush()


def attach(pane_id: str) -> int:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    return asyncio.run(_attach(pane_id))


async def _attach(pane_id: str) -> int:
    info = ensure_daemon()
    url = f"http://127.0.0.1:{info['port']}/ws?token={info['token']}&label=dr-attach"
    loop = asyncio.get_running_loop()
    keys: asyncio.Queue[str] = asyncio.Queue()

    def read_stdin() -> None:
        while True:
            try:
                data = os.read(sys.stdin.fileno(), 1024)
            except OSError:
                data = b""
            loop.call_soon_threadsafe(keys.put_nowait, data.decode("utf-8", "replace") if data else DETACH)
            if not data:
                return

    async with aiohttp.ClientSession() as http, http.ws_connect(url) as ws:
        cols, rows = shutil.get_terminal_size()
        await ws.send_str(json.dumps({"t": "rpc", "id": 1, "method": "pane.resize",
                                      "params": {"pane": pane_id, "cols": cols, "rows": rows}}))
        await ws.send_str(json.dumps({"t": "attach", "pane": pane_id}))
        with RawTerminal():
            threading.Thread(target=read_stdin, daemon=True).start()
            reader = asyncio.create_task(_pump_output(ws, pane_id))
            try:
                while not reader.done():
                    key = await keys.get()
                    if DETACH in key:
                        break
                    await ws.send_str(json.dumps({"t": "in", "pane": pane_id, "data": key}))
            finally:
                reader.cancel()
    return 0


async def _pump_output(ws, pane_id: str) -> None:
    out = sys.stdout
    async for msg in ws:
        if msg.type != aiohttp.WSMsgType.TEXT:
            break
        data = json.loads(msg.data)
        if data.get("t") in ("out", "replay") and data.get("pane") == pane_id:
            out.write(data["data"])
            out.flush()
        elif (data.get("t") == "ev" and data.get("name") == "status" and data["data"]["pane"]["id"] == pane_id
              and data["data"]["new"] == "exited"):
            return
