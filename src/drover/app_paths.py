"""Filesystem locations for config, state and logs (per-user, cross-platform)."""

from __future__ import annotations

import os
from pathlib import Path

APP = "drover"


def _default_dir(kind: str) -> Path:
    """On Windows platformdirs returns LOCALAPPDATA/drover for both; skip its ~60 ms import there."""
    local = os.environ.get("LOCALAPPDATA")
    if os.name == "nt" and local:
        path = Path(local) / APP
    else:
        from platformdirs import user_config_dir, user_state_dir

        path = Path((user_config_dir if kind == "config" else user_state_dir)(APP, appauthor=False))
    from drover.legacy_herd_migration import move_legacy_dir

    move_legacy_dir(path)  # keeps settings and sessions from installs made under the old "herd" name
    return path


def config_dir() -> Path:
    override = os.environ.get("DROVER_CONFIG_DIR")
    path = Path(override) if override else _default_dir("config")
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_dir() -> Path:
    override = os.environ.get("DROVER_STATE_DIR")
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


def web_root() -> Path:
    """Where the UI files from the drover-web repo are unpacked (`web/` static files, `web_dist/` React build)."""
    env = os.environ.get("DROVER_WEB_DIR")
    return Path(env) if env else Path(__file__).parent


def web_static_dir() -> Path:
    return web_root() / "web"


def web_dist_dir() -> Path:
    """Vite build output of the React UI, built and released by drover-web."""
    return web_root() / "web_dist"


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
