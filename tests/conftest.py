"""Shared fixtures.

Every test gets private DROVER_STATE_DIR / DROVER_CONFIG_DIR folders under tmp_path so the real user
config, the real session file and any daemon the user runs are never touched.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path

import pytest
import pytest_asyncio
from daemon_harness import Daemon, boot_daemon
from external_daemon_harness import boot_external_daemon, external_bin
from git_helpers import run_git


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A real git repo on branch `main` with one commit (no remote)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "-b", "main")
    run_git(repo, "config", "user.email", "qa@example.com")
    run_git(repo, "config", "user.name", "drover-qa")
    run_git(repo, "config", "commit.gpgsign", "false")
    (repo / "README.md").write_text("hello\n", encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-m", "init")
    return repo


@pytest.fixture(autouse=True)
def drover_dirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    state = tmp_path / "drover-state"
    config = tmp_path / "drover-config"
    state.mkdir()
    config.mkdir()
    monkeypatch.setenv("DROVER_STATE_DIR", str(state))
    monkeypatch.setenv("DROVER_CONFIG_DIR", str(config))
    return tmp_path


@pytest_asyncio.fixture(loop_scope="function")
async def start_daemon(drover_dirs: Path) -> AsyncIterator[Callable[..., object]]:
    """Boot the real daemon app in-process. Optional settings.toml text is written first."""
    running: list[Daemon] = []

    async def _start(settings_toml: str = "") -> Daemon:
        if settings_toml:
            config = Path(drover_dirs / "drover-config")
            (config / "settings.toml").write_text(settings_toml, encoding="utf-8")
        cmd = external_bin()
        daemon = await (boot_external_daemon(cmd) if cmd else boot_daemon())
        running.append(daemon)
        return daemon

    yield _start
    for daemon in running:
        await daemon.shutdown()
