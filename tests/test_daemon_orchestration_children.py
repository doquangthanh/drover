"""Herdr-style orchestration on a real daemon: parent notes, `dr send parent`, wait --children, helpers stopping
with their parent. Runs against the Python daemon and, in conformance mode, the Rust one.

The agents are a small fake (`fakeagent`): it reports its state over OSC 7501 and prints every line it receives as
`GOT:<line>`, so a test can see what the daemon typed into it.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

import pytest
from daemon_harness import wait_for_text

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the fake agent is a POSIX script")

FAKE_AGENT = r'''#!/usr/bin/env python3
"""Fake coding agent. Commands (argv[1] = first task, then stdin lines): work N, late D N, quit."""
import sys, time

def report(state):
    sys.stdout.write("\x1b]7501;state=%s\x07" % state)
    sys.stdout.flush()

def handle(line):
    words = line.split()
    if words[:1] == ["work"]:
        report("working"); time.sleep(float(words[1])); report("done"); print("FINISHED", flush=True)
    elif words[:1] == ["late"]:
        time.sleep(float(words[1])); handle("work " + words[2])
    elif words[:1] == ["quit"]:
        sys.exit(3)

print("READY", flush=True)
report("idle")
if len(sys.argv) > 1:
    handle(sys.argv[1])
for raw in sys.stdin:
    line = raw.strip()
    print("GOT:" + line, flush=True)
    handle(line)
'''

RULES = '''id = "fakeagent"

[[rules]]
id = "never"
state = "working"
priority = 1
region = "bottom(3)"
regex = ['THIS-NEVER-SHOWS-UP']
'''


@pytest.fixture
def fake_agent(drover_dirs: Path) -> str:
    folder = drover_dirs / "bin"
    folder.mkdir()
    script = folder / "fakeagent"
    script.write_text(FAKE_AGENT, encoding="utf-8")
    script.chmod(0o755)
    rules = drover_dirs / "drover-config" / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    (rules / "fakeagent.toml").write_text(RULES, encoding="utf-8")
    return str(script)


async def _create(daemon, cwd: Path, name: str, command: str, caller: str | None = None, **extra) -> str:
    params = {"command": command, "cwd": str(cwd), "name": name, **extra}
    if caller:
        params["caller"] = caller
    _, body = await daemon.call("pane.create", params)
    assert "result" in body, body
    return body["result"]["id"]


async def _screen(daemon, pane_id: str) -> str:
    _, body = await daemon.call("pane.read", {"pane": pane_id})
    return body["result"]["text"]


async def test_parent_agent_gets_a_note_when_its_helper_exits(start_daemon, drover_dirs, fake_agent):
    daemon = await start_daemon()
    parent = await _create(daemon, drover_dirs, "lead", fake_agent)
    await wait_for_text(daemon, parent, "READY")
    child = await _create(daemon, drover_dirs, "helper", f"{fake_agent} quit", caller=parent)
    await wait_for_text(daemon, parent, f'GOT:<dr from="{child} helper" state="exited">exited (exit code 3)</dr>')


async def test_no_note_is_typed_into_a_shell_parent(start_daemon, drover_dirs, fake_agent):
    daemon = await start_daemon()
    parent = await _create(daemon, drover_dirs, "sh-lead", "sh")
    child = await _create(daemon, drover_dirs, "helper", f"{fake_agent} quit", caller=parent)
    _, body = await daemon.call("pane.wait", {"pane": child, "states": ["exited"], "timeout": 10})
    assert body["result"]["state"] == "exited"
    await asyncio.sleep(1.5)
    assert "<dr from" not in await _screen(daemon, parent)


async def test_a_half_typed_message_holds_the_note_until_enter(start_daemon, drover_dirs, fake_agent):
    daemon = await start_daemon()
    parent = await _create(daemon, drover_dirs, "lead", fake_agent)
    await wait_for_text(daemon, parent, "READY")
    await daemon.call("pane.write", {"pane": parent, "data": "half typ"})  # the person, from the UI
    child = await _create(daemon, drover_dirs, "helper", f"{fake_agent} quit", caller=parent)
    await daemon.call("pane.wait", {"pane": child, "states": ["exited"], "timeout": 10})
    await asyncio.sleep(1.5)
    assert "<dr from" not in await _screen(daemon, parent)
    await daemon.call("pane.write", {"pane": parent, "data": "ed\r"})
    text = await wait_for_text(daemon, parent, 'state="exited"')
    assert "GOT:half typed" in text


async def test_a_wait_on_the_helper_replaces_the_note(start_daemon, drover_dirs, fake_agent):
    daemon = await start_daemon()
    parent = await _create(daemon, drover_dirs, "lead", fake_agent)
    await wait_for_text(daemon, parent, "READY")
    child = await _create(daemon, drover_dirs, "helper", f"{fake_agent} 'late 5 1'", caller=parent)
    _, body = await daemon.call("pane.wait", {"pane": child, "states": ["done"], "timeout": 20, "caller": parent})
    assert body["result"]["state"] == "done", body
    await asyncio.sleep(1.5)
    assert "<dr from" not in await _screen(daemon, parent)


async def test_dr_send_parent_reaches_the_parent_tagged_with_the_helper(start_daemon, drover_dirs, fake_agent):
    daemon = await start_daemon()
    parent = await _create(daemon, drover_dirs, "lead", fake_agent)
    child = await _create(daemon, drover_dirs, "helper", fake_agent, caller=parent)
    await wait_for_text(daemon, parent, "READY")
    _, body = await daemon.call("pane.send", {"pane": "parent", "text": "2 bugs found", "caller": child})
    assert body["result"]["pane"] == parent
    await wait_for_text(daemon, parent, f'GOT:<dr from="{child} helper">2 bugs found</dr>')


async def test_parent_target_needs_a_parent(start_daemon, drover_dirs, fake_agent):
    daemon = await start_daemon()
    lone = await _create(daemon, drover_dirs, "lone", fake_agent)
    _, body = await daemon.call("pane.send", {"pane": "parent", "text": "x", "caller": lone})
    assert body["error"]["code"] == 5


async def test_helpers_stop_with_their_parent_unless_they_outlive_it(start_daemon, drover_dirs, fake_agent):
    daemon = await start_daemon()
    parent = await _create(daemon, drover_dirs, "lead", fake_agent)
    child = await _create(daemon, drover_dirs, "helper", fake_agent, caller=parent)
    keeper = await _create(daemon, drover_dirs, "keeper", fake_agent, caller=parent, outlive_parent=True)
    await wait_for_text(daemon, child, "READY")
    await wait_for_text(daemon, keeper, "READY")
    await daemon.call("pane.send", {"pane": parent, "text": "quit"})
    _, body = await daemon.call("pane.wait", {"pane": child, "states": ["exited"], "timeout": 10})
    assert body["result"]["state"] == "exited", body
    await asyncio.sleep(1)
    _, panes = await daemon.call("pane.list")
    state = {p["id"]: p["state"] for p in panes["result"]}
    assert state[keeper] != "exited"


async def test_wait_children_without_helpers(start_daemon, drover_dirs, fake_agent):
    daemon = await start_daemon()
    lone = await _create(daemon, drover_dirs, "lone", fake_agent)
    _, body = await daemon.call("pane.wait_children", {"caller": lone, "mode": "all", "timeout": 5})
    assert body["result"] == {"reason": "no_children", "children": []}
    _, body = await daemon.call("pane.wait_children", {"mode": "all"})
    assert body["error"]["code"] == 5


async def test_wait_children_any_returns_the_first_helper_with_news(start_daemon, drover_dirs, fake_agent):
    daemon = await start_daemon()
    parent = await _create(daemon, drover_dirs, "lead", fake_agent)
    slow = await _create(daemon, drover_dirs, "slow", f"{fake_agent} 'work 30'", caller=parent)
    quick = await _create(daemon, drover_dirs, "quick", f"{fake_agent} 'work 2'", caller=parent)
    await wait_for_text(daemon, quick, "READY")
    _, body = await daemon.call("pane.wait_children", {"caller": parent, "mode": "any", "timeout": 20})
    result = body["result"]
    assert (result["reason"], result["pane"], result["state"]) == ("child", quick, "done"), result
    assert {c["pane"] for c in result["children"]} == {slow, quick}


async def test_wait_children_all_returns_once_no_helper_works(start_daemon, drover_dirs, fake_agent):
    daemon = await start_daemon()
    parent = await _create(daemon, drover_dirs, "lead", fake_agent)
    await _create(daemon, drover_dirs, "a", f"{fake_agent} 'work 1'", caller=parent)
    await _create(daemon, drover_dirs, "b", f"{fake_agent} 'work 3'", caller=parent)
    started = time.monotonic()
    _, body = await daemon.call("pane.wait_children", {"caller": parent, "mode": "all", "timeout": 30})
    result = body["result"]
    assert result["reason"] == "all", result
    assert time.monotonic() - started >= 2.5
    assert all(c["state"] != "working" for c in result["children"])


async def test_wait_children_times_out_with_code_2(start_daemon, drover_dirs, fake_agent):
    daemon = await start_daemon()
    parent = await _create(daemon, drover_dirs, "lead", fake_agent)
    await _create(daemon, drover_dirs, "slow", f"{fake_agent} 'work 30'", caller=parent)
    _, body = await daemon.call("pane.wait_children", {"caller": parent, "mode": "all", "timeout": 1})
    assert body["error"]["code"] == 2
