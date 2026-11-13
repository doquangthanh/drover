"""Daemon pane spawn edge cases: failed launches and quoted executable paths on Windows."""

from __future__ import annotations

from pathlib import Path

from daemon_harness import wait_for_text


async def test_missing_command_returns_general_error_with_message(start_daemon, herd_dirs: Path):
    daemon = await start_daemon()
    _, body = await daemon.call("pane.create", {"command": "definitely-missing-xyz --flag", "cwd": str(herd_dirs)})
    assert body["error"]["code"] == 1
    assert "not found" in body["error"]["message"]


async def test_failed_spawn_leaves_no_empty_tab(start_daemon, herd_dirs: Path):
    # Expected to FAIL: create_tab() runs before pane.start(), so a spawn error leaves a tab with
    # layout=None behind in state.get. Source: herd/core/session_manager.py:76-89 (create_pane).
    daemon = await start_daemon()
    await daemon.call("pane.create", {"command": "definitely-missing-xyz", "cwd": str(herd_dirs)})
    _, state = await daemon.call("state.get")
    assert state["result"]["tabs"] == []


async def test_quoted_executable_path_with_spaces_spawns(start_daemon, herd_dirs: Path):
    # Expected to FAIL: split_command() on Windows (shlex posix=False) keeps the literal quotes, so
    # shutil.which and winpty both receive '"...\my tools\hello tool.cmd"' and cannot find it.
    # Source: herd/pty/pty_backend_factory.py:36 (split_command), used by session_manager.py:73.
    tools = herd_dirs / "my tools"
    tools.mkdir()
    tool = tools / "hello tool.cmd"
    tool.write_text("@echo off\r\necho quoted-path-ok %1\r\n", encoding="utf-8")
    daemon = await start_daemon()
    _, body = await daemon.call("pane.create", {"command": f'"{tool}" arg1', "cwd": str(herd_dirs)})
    assert "result" in body, body
    await wait_for_text(daemon, body["result"]["id"], "quoted-path-ok")
