"""Chat RPC through the real daemon app: creating, listing, history, validation. (No real Claude is started.)"""

from __future__ import annotations

from pathlib import Path


async def test_create_list_history_rename_remove(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    folder = drover_dirs / "proj"
    folder.mkdir()
    _, body = await daemon.call("chat.create", {"cwd": str(folder), "name": "notes", "permission_mode": "acceptEdits"})
    chat = body["result"]
    assert chat["id"] == "c1" and chat["name"] == "notes" and chat["state"] == "idle" and chat["permission_mode"] == "acceptEdits"

    _, body = await daemon.call("chat.list", {})
    assert [c["id"] for c in body["result"]] == ["c1"]
    _, body = await daemon.call("state.get", {})  # snapshot of the whole workspace also carries the chats
    _, hist = await daemon.call("chat.history", {"chat": "c1"})
    assert hist["result"]["items"] == []

    await daemon.call("chat.rename", {"chat": "c1", "name": "renamed"})
    _, body = await daemon.call("chat.list", {})
    assert body["result"][0]["name"] == "renamed"

    await daemon.call("chat.remove", {"chat": "c1"})
    _, body = await daemon.call("chat.list", {})
    assert body["result"] == []


async def test_bad_input_is_refused_with_clear_errors(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    _, body = await daemon.call("chat.create", {"cwd": str(drover_dirs / "nope")})
    assert body["error"]["code"] == 5 and "not a folder" in body["error"]["message"]
    _, body = await daemon.call("chat.send", {"chat": "c9", "text": "hi"})
    assert body["error"]["code"] == 3

    folder = drover_dirs / "proj"
    folder.mkdir()
    await daemon.call("chat.create", {"cwd": str(folder)})
    _, body = await daemon.call("chat.send", {"chat": "c1"})
    assert body["error"]["code"] == 5 and "nothing to send" in body["error"]["message"]
    _, body = await daemon.call("chat.send", {"chat": "c1", "images": [{"media_type": "image/svg+xml", "data": "AA"}]})
    assert body["error"]["code"] == 5 and "media_type" in body["error"]["message"]
    _, body = await daemon.call("chat.send", {"chat": "c1", "images": [{"media_type": "image/png", "data": "A" * 14_000_001}]})
    assert body["error"]["code"] == 5 and "10 MB" in body["error"]["message"]
    _, body = await daemon.call("chat.set_mode", {"chat": "c1", "permission_mode": "yolo"})
    assert body["error"]["code"] == 5
    _, body = await daemon.call("chat.answer", {"chat": "c1", "request": "zzz", "allow": True})
    assert body["result"] == {"ok": False}


async def test_files_endpoint_ranks_project_files_and_set_model_is_saved(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    folder = drover_dirs / "proj"
    (folder / "src").mkdir(parents=True)
    (folder / "src" / "pricing.tsx").write_text("x", encoding="utf-8")
    (folder / "README.md").write_text("x", encoding="utf-8")
    await daemon.call("chat.create", {"cwd": str(folder)})
    _, body = await daemon.call("chat.files", {"chat": "c1", "query": "pric"})
    assert body["result"]["files"] == ["src/pricing.tsx"]
    _, body = await daemon.call("chat.files", {"chat": "c1"})
    assert body["result"]["files"][0] == "README.md"
    await daemon.call("chat.set_model", {"chat": "c1", "model": "opus"})
    _, body = await daemon.call("chat.list", {})
    assert body["result"][0]["model"] == "opus"
    _, body = await daemon.call("chat.files", {"chat": "c9"})
    assert body["error"]["code"] == 3
