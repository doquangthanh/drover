"""Finding the native claude.exe: on PATH, behind an npm shim, in ~/.local/bin; and doing nothing off Windows."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from drover.chat import claude_locator as cl

windows_only = pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific lookup")


def touch(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x")
    return str(path)


@windows_only
def test_native_exe_on_path_wins(tmp_path):
    exe = touch(tmp_path / "bin" / "claude.exe")
    assert cl.find_claude_exe(str(tmp_path / "bin"), tmp_path / "home") == exe


@windows_only
def test_npm_shim_leads_to_the_real_exe_in_the_package(tmp_path):
    npm = tmp_path / "npm"
    touch(npm / "claude.cmd")
    real = touch(npm / cl.NPM_PACKAGE_EXE)
    assert cl.find_claude_exe(str(npm), tmp_path / "home") == real


@windows_only
def test_shim_without_the_package_exe_is_not_enough(tmp_path):
    npm = tmp_path / "npm"
    touch(npm / "claude.cmd")
    assert cl.find_claude_exe(str(npm), tmp_path / "home") is None


@windows_only
def test_falls_back_to_the_native_installer_location(tmp_path):
    home = tmp_path / "home"
    exe = touch(home / ".local" / "bin" / "claude.exe")
    assert cl.find_claude_exe("", home) == exe


@windows_only
def test_relative_and_empty_path_entries_are_ignored(tmp_path, monkeypatch):
    touch(tmp_path / "claude.exe")
    monkeypatch.chdir(tmp_path)
    assert cl.find_claude_exe(os.pathsep.join(["", "."]), tmp_path / "home") is None


def test_other_systems_leave_it_to_the_sdk(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "platform", "linux")
    assert cl.find_claude_exe(str(tmp_path), tmp_path) is None
