"""Keep the Agent SDK's `claude.exe` child from popping up a console window on Windows.

drover runs windowed / detached (no console), so a console-subsystem child gets a brand-new visible terminal. The
SDK spawns it through `anyio.open_process` without creation flags and offers no hook, so we wrap that call to add
CREATE_NO_WINDOW (drover starts no other anyio subprocesses).
"""

from __future__ import annotations

import subprocess
import sys
from typing import Any

_patched = False


def hide_sdk_console() -> None:
    global _patched
    if _patched or sys.platform != "win32":
        return
    _patched = True
    import anyio

    original = anyio.open_process

    async def open_process_hidden(*args: Any, **kwargs: Any) -> Any:
        kwargs["creationflags"] = kwargs.get("creationflags", 0) | subprocess.CREATE_NO_WINDOW
        return await original(*args, **kwargs)

    anyio.open_process = open_process_hidden
