"""Linux/macOS backend via ptyprocess; reads are driven by the event loop (add_reader)."""

from __future__ import annotations

import asyncio
import codecs
import logging
import os

from drover.pty.pty_backend_interface import ExitCallback, OutputCallback, PtyBackend

log = logging.getLogger(__name__)


class PosixPtyBackend(PtyBackend):
    def __init__(self, on_output: OutputCallback, on_exit: ExitCallback) -> None:
        super().__init__(on_output, on_exit)
        self._proc = None
        self._loop = asyncio.get_running_loop()
        self._decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self._closed = False

    def spawn(self, argv: list[str], cwd: str, env: dict[str, str], cols: int, rows: int) -> None:
        from ptyprocess import PtyProcess

        self._proc = PtyProcess.spawn(argv, cwd=cwd, env=env, dimensions=(rows, cols))
        self.pid = self._proc.pid
        os.set_blocking(self._proc.fd, False)
        self._loop.add_reader(self._proc.fd, self._on_readable)

    def _on_readable(self) -> None:
        try:
            chunk = os.read(self._proc.fd, 65536)
        except BlockingIOError:
            return
        except OSError:
            chunk = b""
        if chunk:
            text = self._decoder.decode(chunk)
            if text:
                self.on_output(text)
            return
        self._finish()

    def _finish(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._loop.remove_reader(self._proc.fd)
        code = None
        try:
            self._proc.wait()
            code = self._proc.exitstatus
        except Exception:
            pass
        self.on_exit(code)

    def write(self, data: str) -> None:
        if self._proc is not None and not self._closed:
            try:
                os.write(self._proc.fd, data.encode("utf-8"))
            except OSError as exc:
                log.debug("pty write failed: %s", exc)

    def resize(self, cols: int, rows: int) -> None:
        if self._proc is not None and not self._closed:
            try:
                self._proc.setwinsize(rows, cols)
            except OSError:
                pass

    def kill(self) -> None:
        if self._proc is not None:
            try:
                self._proc.terminate(force=True)
            except Exception:
                pass

    def is_alive(self) -> bool:
        return bool(self._proc and not self._closed and self._proc.isalive())
