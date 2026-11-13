"""Start the herd daemon when the user signs in (Windows Startup folder / systemd --user)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from herd.self_command import hd_command


def set_autostart(enabled: bool) -> str:
    if sys.platform == "win32":
        startup = Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup"
        script = startup / "herd-daemon.cmd"
        if not enabled:
            script.unlink(missing_ok=True)
            return "autostart off"
        quoted = " ".join(f'"{a}"' for a in hd_command(windowless=True))
        script.write_text(f'@start "" {quoted} server run --background\r\n', encoding="utf-8")
        return f"autostart on ({script})"
    unit_dir = Path.home() / ".config/systemd/user"
    unit = unit_dir / "herd.service"
    if not enabled:
        subprocess.run(["systemctl", "--user", "disable", "--now", "herd.service"], check=False)
        unit.unlink(missing_ok=True)
        return "autostart off"
    unit_dir.mkdir(parents=True, exist_ok=True)
    unit.write_text(
        "[Unit]\nDescription=herd agent daemon\n\n[Service]\n"
        f"ExecStart={' '.join(hd_command())} server run --background\nRestart=on-failure\n\n"
        "[Install]\nWantedBy=default.target\n",
        encoding="utf-8",
    )
    subprocess.run(["systemctl", "--user", "enable", "--now", "herd.service"], check=False)
    return f"autostart on ({unit})"
