"""Daemon pane spawn edge cases: failed launches and quoted executable paths with spaces."""

from __future__ import annotations

import sys
from pathlib import Path

from daemon_harness import wait_for_text


async def test_missing_command_returns_general_error_with_message(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    _, body = await daemon.call("pane.create", {"command": "definitely-missing-xyz --flag", "cwd": str(drover_dirs)})
    assert body["error"]["code"] == 1
    assert "not found" in body["error"]["message"]


async def test_failed_spawn_leaves_no_empty_tab(start_daemon, drover_dirs: Path):
    # Expected to FAIL: create_tab() runs before pane.start(), so a spawn error leaves a tab with
    # layout=None behind in state.get. Source: drover/core/session_manager.py:76-89 (create_pane).
    daemon = await start_daemon()
    await daemon.call("pane.create", {"command": "definitely-missing-xyz", "cwd": str(drover_dirs)})
    _, state = await daemon.call("state.get")
    assert state["result"]["tabs"] == []


async def test_quoted_executable_path_with_spaces_spawns(start_daemon, drover_dirs: Path):
    # split_command() must drop the quotes so the path with spaces reaches the PTY as one argument.
    tools = drover_dirs / "my tools"
    tools.mkdir()
    if sys.platform == "win32":
        tool = tools / "hello tool.cmd"
        tool.write_text("@echo off\r\necho quoted-path-ok %1\r\n", encoding="utf-8")
    else:
        tool = tools / "hello tool"
        tool.write_text('#!/bin/sh\necho quoted-path-ok "$1"\n', encoding="utf-8")
        tool.chmod(0o755)
    daemon = await start_daemon()
    _, body = await daemon.call("pane.create", {"command": f'"{tool}" arg1', "cwd": str(drover_dirs)})
    assert "result" in body, body
    await wait_for_text(daemon, body["result"]["id"], "quoted-path-ok")


async def test_space_create_new_always_makes_a_fresh_space(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    _, first = await daemon.call("space.create", {"cwd": str(drover_dirs), "new": True})
    _, second = await daemon.call("space.create", {"cwd": str(drover_dirs), "new": True})
    _, reused = await daemon.call("space.create", {"cwd": str(drover_dirs)})
    assert first["result"]["space_id"] != second["result"]["space_id"]
    assert reused["result"]["space_id"] == first["result"]["space_id"]
    _, state = await daemon.call("state.get")
    names = sorted(s["name"] for s in state["result"]["spaces"])
    assert names == sorted([drover_dirs.name, f"{drover_dirs.name}-2"])


async def test_space_create_without_cwd_opens_home(start_daemon):
    daemon = await start_daemon()
    _, body = await daemon.call("space.create", {"new": True})
    assert "result" in body, body
    assert Path(body["result"]["pane"]["cwd"]) == Path.home()
