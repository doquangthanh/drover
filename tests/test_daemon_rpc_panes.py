"""Daemon HTTP API integration: auth, real ConPTY panes, input/output, error codes."""

from __future__ import annotations

from pathlib import Path

from daemon_harness import wait_for_text

HELLO_CMD = "cmd /c echo hello-herd & ping -n 3 127.0.0.1 >nul"


async def test_health_and_index_are_public(start_daemon):
    daemon = await start_daemon()
    health = await daemon.client.get("/health")
    assert await health.json() == {"ok": True, "app": "herd"}
    index = await daemon.client.get("/")
    assert index.status == 200
    assert index.headers["Cache-Control"] == "no-store"


async def test_rpc_rejects_missing_token(start_daemon):
    daemon = await start_daemon()
    resp = await daemon.client.post("/rpc", json={"method": "server.info", "params": {}})
    assert resp.status == 401


async def test_rpc_rejects_wrong_token(start_daemon):
    daemon = await start_daemon()
    status, _ = await daemon.call("server.info", token="not-the-token")
    assert status == 401


async def test_server_info_reports_version_and_no_agents(start_daemon):
    daemon = await start_daemon()
    _, body = await daemon.call("server.info")
    assert body["result"]["version"] == "0.1.0"
    assert body["result"]["counts"] == {}


async def test_unknown_method_returns_no_method_error(start_daemon):
    daemon = await start_daemon()
    _, body = await daemon.call("pane.teleport")
    assert body["error"]["code"] == -32601


async def test_pane_create_runs_command_and_output_is_readable(start_daemon, herd_dirs: Path):
    daemon = await start_daemon()
    cwd = herd_dirs / "work"
    cwd.mkdir()
    _, body = await daemon.call("pane.create", {"command": HELLO_CMD, "cwd": str(cwd), "name": "hello"})
    pane = body["result"]
    assert pane["id"].startswith("%")
    assert pane["name"] == "hello"
    assert pane["kind"] == "shell"
    await wait_for_text(daemon, pane["id"], "hello-herd")


async def test_pane_list_includes_created_pane(start_daemon, herd_dirs: Path):
    daemon = await start_daemon()
    _, created = await daemon.call("pane.create", {"command": "cmd /k", "cwd": str(herd_dirs), "name": "listed"})
    pane_id = created["result"]["id"]
    _, listing = await daemon.call("pane.list")
    assert pane_id in [p["id"] for p in listing["result"]]


async def test_pane_send_types_into_interactive_shell(start_daemon, herd_dirs: Path):
    daemon = await start_daemon()
    _, created = await daemon.call("pane.create", {"command": "cmd /k", "cwd": str(herd_dirs), "name": "typist"})
    pane_id = created["result"]["id"]
    # "ty^ped" is echoed as typed, but cmd prints the caret-free "typed-herd" only when it runs the line.
    _, sent = await daemon.call("pane.send", {"pane": pane_id, "text": "echo ty^ped-herd"})
    assert sent["result"] == {"pane": pane_id}
    await wait_for_text(daemon, pane_id, "typed-herd")


async def test_pane_wait_times_out_with_code_2(start_daemon, herd_dirs: Path):
    daemon = await start_daemon()
    _, created = await daemon.call("pane.create", {"command": "cmd /k", "cwd": str(herd_dirs), "name": "quiet"})
    pane_id = created["result"]["id"]
    _, body = await daemon.call("pane.wait", {"pane": pane_id, "states": ["done"], "timeout": 0.5})
    assert body["error"]["code"] == 2
    assert "timed out" in body["error"]["message"]


async def test_pane_wait_returns_exited_when_process_ends(start_daemon, herd_dirs: Path):
    daemon = await start_daemon()
    _, created = await daemon.call("pane.create", {"command": "cmd /c echo bye", "cwd": str(herd_dirs)})
    pane_id = created["result"]["id"]
    _, body = await daemon.call("pane.wait", {"pane": pane_id, "timeout": 15})
    assert body["result"] == {"pane": pane_id, "state": "exited"}


async def test_pane_close_removes_it_and_later_reads_are_not_found(start_daemon, herd_dirs: Path):
    daemon = await start_daemon()
    _, created = await daemon.call("pane.create", {"command": "cmd /k", "cwd": str(herd_dirs), "name": "closing"})
    pane_id = created["result"]["id"]
    _, closed = await daemon.call("pane.close", {"pane": pane_id})
    assert "error" not in closed
    _, listing = await daemon.call("pane.list")
    assert pane_id not in [p["id"] for p in listing["result"]]
    _, body = await daemon.call("pane.read", {"pane": pane_id})
    assert body["error"]["code"] == 3


async def test_pane_create_rejects_missing_folder(start_daemon, herd_dirs: Path):
    daemon = await start_daemon()
    _, body = await daemon.call("pane.create", {"command": "cmd /k", "cwd": str(herd_dirs / "nope")})
    assert body["error"]["code"] == 5
    assert "does not exist" in body["error"]["message"]


async def test_pane_limit_from_settings_returns_policy_error(start_daemon, herd_dirs: Path):
    daemon = await start_daemon("[orchestration]\nmax_panes = 1\n")
    _, first = await daemon.call("pane.create", {"command": "cmd /k", "cwd": str(herd_dirs)})
    assert "result" in first
    _, second = await daemon.call("pane.create", {"command": "cmd /k", "cwd": str(herd_dirs)})
    assert second["error"]["code"] == 4
    assert "pane limit" in second["error"]["message"]


async def test_missing_required_parameter_is_bad_params(start_daemon):
    daemon = await start_daemon()
    _, body = await daemon.call("pane.write", {"data": "x"})
    assert body["error"]["code"] == 5
    assert "missing parameter: pane" in body["error"]["message"]


async def test_rpc_non_ascii_token_is_401_not_500(start_daemon):
    # Expected to FAIL: hmac.compare_digest(str, str) raises TypeError on non-ASCII input, so the
    # request dies as a 500 instead of a clean 401. Source: herd/daemon/web_server.py:25 (_token_ok).
    daemon = await start_daemon()
    status, _ = await daemon.call("server.info", token="tökén")
    assert status == 401
