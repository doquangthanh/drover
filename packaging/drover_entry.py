"""PyInstaller entry for drover(.exe): no args opens the desktop window, otherwise it is the `dr` CLI/daemon."""

import sys

if sys.platform == "win32" and len(sys.argv) > 1:
    # Windowed exe has no console: attach to the parent's so `drover status` etc. can print.
    import ctypes
    import os

    if ctypes.windll.kernel32.AttachConsole(-1):
        for fd, name, mode in ((1, "CONOUT$", "w"), (2, "CONOUT$", "w")):
            try:
                os.fstat(fd)
            except OSError:  # only when not redirected
                stream = open(name, mode, encoding="utf-8", buffering=1)  # noqa: SIM115
                setattr(sys, "stdout" if fd == 1 else "stderr", stream)

if len(sys.argv) > 1:
    from drover.cli.cli_main import main

    main()
else:
    # Not cli_main: with Textual bundled, a bare `dr` opens the terminal UI, which has no terminal to draw in
    # when the menu or desktop icon starts drover, so the app seemed not to open at all.
    from drover.desktop.desktop_window_launcher import main as open_app

    open_app()
