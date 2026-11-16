"""DaemonConnection against a real daemon (daemon_harness): state push, rpc, attach/replay/out, errors."""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from drover.tui.daemon_ws_connection import DaemonConnection, RpcError, wait_connected


async def _until(predicate, timeout: float = 15.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < deadline, "condition not reached"
        await asyncio.sleep(0.05)


@pytest_asyncio.fixture(loop_scope="function")
async def conn(start_daemon):
    daemon = await start_daemon()
    c = DaemonConnection(str(daemon.client.make_url("/")), daemon.token)
    c.states, c.outputs = [], []
    c.on_state = c.states.append
    c.on_output = lambda pane, data, replay: c.outputs.append((pane, data, replay))
    task = asyncio.create_task(c.run())
    await wait_connected(c)
    yield c
    c.stop()
    await asyncio.wait_for(task, 5)


async def test_first_message_is_a_full_state(conn):
    await _until(lambda: conn.states)
    assert {"spaces", "tabs", "panes", "stopped"} <= set(conn.states[0])


async def test_rpc_attach_replay_and_output(conn, tmp_path):
    result = await conn.rpc("pane.create", {"command": "", "cwd": str(tmp_path)})
    pane = result["id"]
    conn.attach(pane)
    await _until(lambda: any(r for _, _, r in conn.outputs))
    conn.send_input(pane, "echo tui-hello-42\r")
    await _until(lambda: any(not r and "tui-hello-42" in d for _, d, r in conn.outputs))


async def test_rpc_error_raises(conn):
    with pytest.raises(RpcError):
        await conn.rpc("pane.focus", {"pane": "%does-not-exist"})


async def test_rpc_without_connection_raises():
    with pytest.raises(RpcError):
        await DaemonConnection("http://127.0.0.1:1", "x").rpc("pane.list")


async def test_unreachable_daemon_reports_disconnected_and_stops():
    c = DaemonConnection("http://127.0.0.1:1", "x")
    task = asyncio.create_task(c.run())
    await asyncio.sleep(0.3)
    assert c.connected is False
    c.stop()
    await asyncio.wait_for(task, 5)
