"""Daemon RPC: pane.prompt, pane.keys, pane.wait_output and alternate-screen history reads on real ConPTY panes."""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from daemon_harness import DEAF, PROMPT_MARK, SHELL, shell_line, wait_for_text

APP = Path(__file__).parent / "scripts" / "alt_screen_transcript_app.py"


async def _shell(daemon, cwd: Path, name: str, command: str = SHELL) -> str:
    _, created = await daemon.call("pane.create", {"command": command, "cwd": str(cwd), "name": name})
    return created["result"]["id"]


async def test_wait_output_matches_regex_and_returns_the_line(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    pane_id = await _shell(daemon, drover_dirs, "tests")
    await daemon.call("pane.send", {"pane": pane_id, "text": shell_line("echo 3 tests pa^ssed")})
    _, body = await daemon.call("pane.wait_output", {"pane": pane_id, "pattern": r"\d+ tests passed",
                                                     "regex": True, "timeout": 15})
    assert body["result"]["matched_line"].strip() == "3 tests passed"
    assert body["result"]["pane"] == pane_id


async def test_wait_output_times_out_with_code_2(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    pane_id = await _shell(daemon, drover_dirs, "quiet")
    _, body = await daemon.call("pane.wait_output", {"pane": pane_id, "pattern": "never-printed", "timeout": 0.6})
    assert body["error"]["code"] == 2


async def test_wait_output_rejects_a_bad_regex(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    pane_id = await _shell(daemon, drover_dirs, "re")
    _, body = await daemon.call("pane.wait_output", {"pane": pane_id, "pattern": "([", "regex": True})
    assert body["error"]["code"] == 5
    assert "bad regex" in body["error"]["message"]


async def test_keys_edit_the_line_and_submit_it(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    pane_id = await _shell(daemon, drover_dirs, "editor")
    await daemon.call("pane.send", {"pane": pane_id, "text": shell_line("echo key^s-okXY"), "enter": False})
    await wait_for_text(daemon, pane_id, shell_line("key^s-okXY"))
    _, body = await daemon.call("pane.keys", {"pane": pane_id, "keys": ["backspace", "backspace", "enter"]})
    assert body["result"] == {"pane": pane_id, "keys": ["backspace", "backspace", "enter"]}
    text = await wait_for_text(daemon, pane_id, "keys-ok")
    assert "keys-okXY" not in text


async def test_keys_rejects_unknown_names(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    pane_id = await _shell(daemon, drover_dirs, "keys")
    _, body = await daemon.call("pane.keys", {"pane": pane_id, "keys": ["hyper+q"]})
    assert body["error"]["code"] == 5
    assert "unknown key" in body["error"]["message"]


async def test_prompt_with_wait_returns_after_the_turn_settles(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    pane_id = await _shell(daemon, drover_dirs, "prompted")
    text = shell_line("echo prom^pt-done")
    _, body = await daemon.call("pane.prompt", {"pane": pane_id, "text": text, "wait": True, "timeout": 30})
    assert "result" in body, body
    assert body["result"]["state"] in ("idle", "done")
    _, read = await daemon.call("pane.read", {"pane": pane_id})
    assert "prompt-done" in read["result"]["text"]


async def test_prompt_refuses_a_blocked_agent_without_typing(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    pane_id = await _shell(daemon, drover_dirs, "asking")
    await wait_for_text(daemon, pane_id, PROMPT_MARK)
    daemon.ctx.manager.get(pane_id).tracker.state = "blocked"  # as if a permission dialog were detected
    _, body = await daemon.call("pane.prompt", {"pane": pane_id, "text": "echo should-not-run"})
    assert body["error"]["code"] == 6
    assert "agent_blocked" in body["error"]["message"]
    _, read = await daemon.call("pane.read", {"pane": pane_id})
    assert "should-not-run" not in read["result"]["text"]


async def test_prompt_reports_stalled_when_nothing_reacts(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    # The program owns the terminal and never reads (or echoes) input, so the prompt causes no output at all.
    pane_id = await _shell(daemon, drover_dirs, "deaf", DEAF)
    pane = daemon.ctx.manager.get(pane_id)
    while time.time() - pane.last_output_at < 1.5:  # let ConPTY finish painting the start-up screen
        await asyncio.sleep(0.2)
    _, body = await daemon.call("pane.prompt", {"pane": pane_id, "text": "hello", "wait": True, "timeout": 30})
    assert "error" in body, body
    assert body["error"]["code"] == 7
    assert "agent_prompt_stalled" in body["error"]["message"]


async def test_read_scrolls_a_full_screen_app_for_history(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    command = f'"{sys.executable}" "{APP}"'
    pane_id = await _shell(daemon, drover_dirs, "fullscreen", command)
    await wait_for_text(daemon, pane_id, "transcript line 199")
    pane = daemon.ctx.manager.get(pane_id)
    assert pane.modes.scrollable_transcript
    pane.tracker.state = "idle"
    _, body = await daemon.call("pane.read", {"pane": pane_id, "lines": 90})
    lines = body["result"]["text"].splitlines()
    assert len(lines) == 90
    assert lines[-1].startswith("> type here")
    assert lines[-2] == "transcript line 199"
    assert lines[0] == "transcript line 111"
    assert sum(1 for line in lines if line.startswith("> type here")) == 1
    # The viewport is back at the bottom afterwards, and our scroll redraws did not count as work.
    await wait_for_text(daemon, pane_id, "transcript line 199")
    await asyncio.sleep(2.5)
    assert pane.state == "idle"
