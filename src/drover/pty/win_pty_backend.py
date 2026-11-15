"""Windows ConPTY backend via pywinpty. Blocking reads run on a daemon thread."""

from __future__ import annotations

import asyncio
import logging
import threading

from drover.pty.pty_backend_interface import ExitCallback, OutputCallback, PtyBackend

log = logging.getLogger(__name__)


class WinPtyBackend(PtyBackend):
    def __init__(self, on_output: OutputCallback, on_exit: ExitCallback) -> None:
        super().__init__(on_output, on_exit)
        self._proc = None
        self._loop = asyncio.get_running_loop()
        self._lock = threading.Lock()

    def spawn(self, argv: list[str], cwd: str, env: dict[str, str], cols: int, rows: int) -> None:
        from winpty import PtyProcess

        self._proc = PtyProcess.spawn(argv, cwd=cwd, env=env, dimensions=(rows, cols))
        self.pid = self._proc.pid
        threading.Thread(target=self._reader, name=f"pty-{self.pid}", daemon=True).start()

    def _reader(self) -> None:
        proc = self._proc
        while True:
            try:
                data = proc.read(65536)
            except EOFError:
                break
            except Exception as exc:  # pywinpty raises various errors on close
                log.debug("pty read ended: %s", exc)
                break
            if data:
                self._loop.call_soon_threadsafe(self.on_output, data)
        code = None
        try:
            proc.wait()
            code = proc.exitstatus
        except Exception:
            pass
        self._loop.call_soon_threadsafe(self.on_exit, code)

    def write(self, data: str) -> None:
        if self._proc is None:
            return
        with self._lock:
            try:
                self._proc.write(data)
            except Exception as exc:
                log.debug("pty write failed: %s", exc)

    def resize(self, cols: int, rows: int) -> None:
        if self._proc is not None and self._proc.isalive():
            try:
                self._proc.setwinsize(rows, cols)
            except Exception as exc:
                log.debug("resize failed: %s", exc)

    def kill(self) -> None:
        if self._proc is not None:
            try:
                self._proc.terminate(force=True)
            except Exception:
                pass

    def is_alive(self) -> bool:
        return bool(self._proc and self._proc.isalive())
