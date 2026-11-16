"""Herdr-style detection: a shell pane becomes an agent while the agent holds its terminal, and back after."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest

from drover.core.foreground_process_probe import agent_kind_from_argv

KINDS = {"claude", "codex", "gemini", "opencode", "shell"}


@pytest.mark.parametrize("argv, kind", [
    (["claude"], "claude"),
    (["/home/me/.local/bin/claude", "--continue"], "claude"),
    (["claude-code"], "claude"),
    (["node", "--no-warnings", "/usr/lib/node_modules/@openai/codex/bin/codex.js"], "codex"),
    (["/bin/sh", "/tmp/x/gemini"], "gemini"),
    (["bash", "-c", "opencode run"], "opencode"),
    (["vim", "claude.md"], None),
    (["zsh"], None),
    (["node", "server.js"], None),
    ([], None),
])
def test_agent_kind_from_argv(argv, kind):
    assert agent_kind_from_argv(argv, KINDS) == kind


async def _pane(daemon, pane_id: str) -> dict:
    _, body = await daemon.call("state.get")
    return next(p for p in body["result"]["panes"] if p["id"] == pane_id)


async def _wait_kind(daemon, pane_id: str, kind: str, timeout: float = 15.0) -> dict:
    deadline = time.monotonic() + timeout
    pane = {}
    while time.monotonic() < deadline:
        pane = await _pane(daemon, pane_id)
        if pane["kind"] == kind:
            return pane
        await asyncio.sleep(0.25)
    raise AssertionError(f"pane kind stayed {pane.get('kind')!r}, wanted {kind!r}")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process groups")
async def test_shell_pane_turns_into_agent_and_back(start_daemon, drover_dirs: Path):
    fake = drover_dirs / "bin" / "claude"
    fake.parent.mkdir()
    fake.write_text("#!/bin/sh\necho fake-claude-up\nsleep 60\n")
    fake.chmod(0o755)
    daemon = await start_daemon()
    _, body = await daemon.call("space.create", {"cwd": str(drover_dirs), "new": True})
    pane_id = body["result"]["pane"]["id"]
    assert body["result"]["pane"]["kind"] == "shell"

    await daemon.call("pane.write", {"pane": pane_id, "data": f"{fake}\r"})
    pane = await _wait_kind(daemon, pane_id, "claude")
    assert pane["name"].startswith("claude")

    await daemon.call("pane.write", {"pane": pane_id, "data": "\x03"})  # Ctrl+C: back to the prompt
    pane = await _wait_kind(daemon, pane_id, "shell")
    assert pane["name"].startswith("shell")


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX process cwd")
async def test_space_follows_folder_and_new_space_starts_there(start_daemon, drover_dirs: Path):
    target = drover_dirs / "proj-follow"
    target.mkdir()
    daemon = await start_daemon()
    _, body = await daemon.call("space.create", {"cwd": str(drover_dirs), "new": True})
    pane_id, space_id = body["result"]["pane"]["id"], body["result"]["space_id"]

    await daemon.call("pane.write", {"pane": pane_id, "data": f"cd {target}\r"})
    deadline = time.monotonic() + 15
    space = {}
    while time.monotonic() < deadline:
        _, state = await daemon.call("state.get")
        space = next(s for s in state["result"]["spaces"] if s["id"] == space_id)
        if space["name"] == "proj-follow":
            break
        await asyncio.sleep(0.25)
    assert space["name"] == "proj-follow" and Path(space["cwd"]) == target.resolve()

    _, body = await daemon.call("space.create", {"new": True, "from": pane_id})
    assert Path(body["result"]["pane"]["cwd"]) == target.resolve()

    await daemon.call("space.rename", {"space": space_id, "name": "mine"})
    await daemon.call("pane.write", {"pane": pane_id, "data": f"cd {drover_dirs}\r"})
    await asyncio.sleep(3)
    _, state = await daemon.call("state.get")
    assert next(s for s in state["result"]["spaces"] if s["id"] == space_id)["name"] == "mine"
