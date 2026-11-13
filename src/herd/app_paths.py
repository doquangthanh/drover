"""Filesystem locations for config, state and logs (per-user, cross-platform)."""

from __future__ import annotations

import os
from pathlib import Path

APP = "herd"


def _default_dir(kind: str) -> Path:
    """On Windows platformdirs returns LOCALAPPDATA/herd for both; skip its ~60 ms import there."""
    local = os.environ.get("LOCALAPPDATA")
    if os.name == "nt" and local:
        return Path(local) / APP
    from platformdirs import user_config_dir, user_state_dir

    return Path((user_config_dir if kind == "config" else user_state_dir)(APP, appauthor=False))


def config_dir() -> Path:
    override = os.environ.get("HERD_CONFIG_DIR")
    path = Path(override) if override else _default_dir("config")
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_dir() -> Path:
    override = os.environ.get("HERD_STATE_DIR")
    path = Path(override) if override else _default_dir("state")
    path.mkdir(parents=True, exist_ok=True)
    return path


def daemon_info_file() -> Path:
    """JSON with port + token of the running daemon. Owner-only permissions."""
    return state_dir() / "daemon.json"


def session_file() -> Path:
    return state_dir() / "session.json"


def log_dir() -> Path:
    path = state_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def user_rules_dir() -> Path:
    path = config_dir() / "rules"
    path.mkdir(parents=True, exist_ok=True)
    return path


def bundled_rules_dir() -> Path:
    return Path(__file__).parent / "status" / "rules"


def web_static_dir() -> Path:
    return Path(__file__).parent / "web"


def restrict_to_owner(path: Path) -> None:
    """Best-effort: make a secret file readable by the current user only."""
    try:
        if os.name == "nt":
            import subprocess

            user = os.environ.get("USERNAME", "")
            subprocess.run(
                ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:F"],
                capture_output=True,
                check=False,
            )
        else:
            path.chmod(0o600)
    except OSError:
        pass
