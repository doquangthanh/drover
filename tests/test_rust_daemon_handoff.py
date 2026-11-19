"""`dr server run` picks the Rust daemon (Windows: the runtime dr.exe) and falls back to Python when it can't start."""

from __future__ import annotations

import sys

import pytest

from drover import self_command
from drover.cli import rust_daemon_handoff as handoff
from drover.core import windows_cli_runtime_installer as rt


@pytest.fixture
def windows_drover_exe(tmp_path, monkeypatch):
    """Pretend to be the onefile drover.exe on Windows."""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", str(tmp_path / "drover.exe"))
    monkeypatch.setattr(self_command, "is_single_exe", lambda: True)
    monkeypatch.delenv("DROVER_ENGINE", raising=False)


def install_runtime() -> str:
    folder = rt.runtime_dir()
    folder.mkdir(parents=True)
    (folder / "dr.exe").write_bytes(b"MZ")
    (folder / rt.DONE_MARKER).write_text("owner", encoding="utf-8")
    return str(folder / "dr.exe")


def test_windows_uses_runtime_dr_exe_once_installed(windows_drover_exe):
    assert handoff.bundled_rust_daemon() is None  # first start of a version: Python daemon installs the runtime
    exe = install_runtime()
    assert handoff.bundled_rust_daemon() == exe


def test_engine_python_and_dr_py_keep_the_python_daemon(windows_drover_exe, monkeypatch):
    install_runtime()
    monkeypatch.setenv("DROVER_ENGINE", "python")
    assert handoff.bundled_rust_daemon() is None
    monkeypatch.delenv("DROVER_ENGINE")
    monkeypatch.setattr(self_command, "is_single_exe", lambda: False)  # dr-py.exe in the runtime folder
    assert handoff.bundled_rust_daemon() is None


def test_source_checkout_never_hands_over(monkeypatch):
    monkeypatch.setattr(sys, "frozen", False, raising=False)
    assert handoff.bundled_rust_daemon() is None


@pytest.mark.skipif(sys.platform != "win32", reason="Windows hand-over spawns the daemon (Linux execs)")
def test_rust_daemon_that_dies_at_start_falls_back_to_python():
    """A 'daemon' that exits at once (cmd /c exit 3) must not leave Drover without one."""
    import os

    cmd = os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe")
    assert handoff.hand_over(cmd, "127.0.0.1", background=True) is None
