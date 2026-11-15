"""A tiny full-screen app for tests: 200 transcript lines on the alternate screen, a fixed footer,
SGR mouse reporting on, and mouse-wheel scrolling of its own viewport (like OpenCode or fullscreen Claude)."""

from __future__ import annotations

import os
import re
import sys

LINES = [f"transcript line {i:03d}" for i in range(200)]
FOOTER = "> type here  (footer)"
WHEEL = re.compile(r"\x1b\[<(\d+);\d+;\d+[Mm]")


def enable_vt_input() -> None:
    """Windows: ask the console to hand us VT sequences (mouse wheel included) instead of input records."""
    if sys.platform != "win32":
        import termios
        import tty

        tty.setraw(sys.stdin.fileno(), termios.TCSANOW)
        return
    import ctypes

    kernel32 = ctypes.windll.kernel32
    handle = kernel32.GetStdHandle(-10)
    mode = ctypes.c_uint32()
    kernel32.GetConsoleMode(handle, ctypes.byref(mode))
    # VT input on; line input, echo and processed input off; quick edit off so the mouse reaches us.
    new = (mode.value | 0x0200 | 0x0080) & ~(0x0002 | 0x0004 | 0x0001 | 0x0040)
    kernel32.SetConsoleMode(handle, new)


def main() -> None:
    rows = os.get_terminal_size().lines
    body_rows = rows - 1
    top = len(LINES) - body_rows
    out = sys.stdout
    out.write("\x1b[?1049h\x1b[?1000h\x1b[?1006h")

    def draw() -> None:
        visible = LINES[top:top + body_rows]
        out.write("\x1b[H\x1b[2J" + "\r\n".join(visible) + f"\x1b[{rows};1H{FOOTER}")
        out.flush()

    enable_vt_input()
    draw()
    buffer = ""
    while True:
        chunk = os.read(sys.stdin.fileno(), 1024).decode("utf-8", "replace")
        if not chunk or "q" in chunk.replace("\x1b", ""):  # a bare q quits
            break
        buffer += chunk
        end = 0
        for match in WHEEL.finditer(buffer):
            button, end = int(match.group(1)), match.end()
            if button == 64:
                top = max(0, top - 1)
            elif button == 65:
                top = min(len(LINES) - body_rows, top + 1)
        rest = buffer[end:]
        buffer = rest[rest.rfind("\x1b"):][-32:] if "\x1b" in rest else ""  # keep a split sequence
        draw()
    out.write("\x1b[?1006l\x1b[?1000l\x1b[?1049l")
    out.flush()


if __name__ == "__main__":
    main()
