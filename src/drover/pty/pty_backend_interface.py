"""Platform-neutral pseudo-terminal contract used by the session manager."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable

OutputCallback = Callable[[str], None]
ExitCallback = Callable[[int | None], None]


class PtyBackend(ABC):
    """One child process attached to a pseudo-terminal.

    Output is delivered as decoded text through `on_output` on the event loop thread;
    `on_exit` fires once with the exit code (None if unknown).
    """

    def __init__(self, on_output: OutputCallback, on_exit: ExitCallback) -> None:
        self.on_output = on_output
        self.on_exit = on_exit
        self.pid: int | None = None

    @abstractmethod
    def spawn(self, argv: list[str], cwd: str, env: dict[str, str], cols: int, rows: int) -> None: ...

    @abstractmethod
    def write(self, data: str) -> None: ...

    @abstractmethod
    def resize(self, cols: int, rows: int) -> None: ...

    @abstractmethod
    def kill(self) -> None: ...

    @abstractmethod
    def is_alive(self) -> bool: ...
