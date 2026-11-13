"""Daemon RPC integration: folder picker sandboxing, config file writes, pane read errors."""

from __future__ import annotations

from pathlib import Path


async def test_fs_list_dirs_inside_allowed_root(start_daemon, herd_dirs: Path):
    root = herd_dirs / "projects"
    (root / "app").mkdir(parents=True)
    (root / "notes.txt").write_text("x", encoding="utf-8")
    daemon = await start_daemon(f'fs_roots = ["{root.as_posix()}"]\n')
    _, body = await daemon.call("fs.list_dirs", {"path": str(root)})
    assert [e["name"] for e in body["result"]["entries"]] == ["app"]
    assert body["result"]["parent"] is None


async def test_fs_list_dirs_outside_allowed_root_is_refused(start_daemon, herd_dirs: Path):
    root = herd_dirs / "projects"
    root.mkdir()
    daemon = await start_daemon(f'fs_roots = ["{root.as_posix()}"]\n')
    _, body = await daemon.call("fs.list_dirs", {"path": str(herd_dirs)})  # parent of the allowed root
    assert body["error"]["code"] == 5
    assert "outside" in body["error"]["message"]


async def test_fs_mkdir_inside_root_creates_folder(start_daemon, herd_dirs: Path):
    root = herd_dirs / "projects"
    root.mkdir()
    daemon = await start_daemon(f'fs_roots = ["{root.as_posix()}"]\n')
    _, body = await daemon.call("fs.mkdir", {"parent": str(root), "name": "fresh"})
    assert Path(body["result"]["path"]).is_dir()


async def test_fs_mkdir_bad_name_is_bad_params(start_daemon, herd_dirs: Path):
    root = herd_dirs / "projects"
    root.mkdir()
    daemon = await start_daemon(f'fs_roots = ["{root.as_posix()}"]\n')
    _, body = await daemon.call("fs.mkdir", {"parent": str(root), "name": "a/b"})
    assert body["error"]["code"] == 5


async def test_settings_write_rejects_invalid_toml(start_daemon):
    daemon = await start_daemon()
    _, body = await daemon.call("settings.write", {"name": "settings.toml", "text": "theme = = 1"})
    assert body["error"]["code"] == 5
    assert "invalid TOML" in body["error"]["message"]


async def test_settings_write_saves_valid_file_into_config_dir(start_daemon, herd_dirs: Path):
    daemon = await start_daemon()
    _, body = await daemon.call("settings.write", {"name": "settings.toml", "text": "scrollback = 777\n"})
    assert "error" not in body
    saved = Path(daemon.ctx.settings.path).read_text(encoding="utf-8")
    assert saved == "scrollback = 777\n"
    assert str(herd_dirs) in str(daemon.ctx.settings.path)


async def test_settings_write_rejects_unknown_file_name(start_daemon):
    daemon = await start_daemon()
    _, body = await daemon.call("settings.write", {"name": "../escape.toml", "text": "x = 1"})
    assert body["error"]["code"] == 5


async def test_pane_read_of_unknown_pane_is_not_found(start_daemon):
    daemon = await start_daemon()
    _, body = await daemon.call("pane.read", {"pane": "%99999"})
    assert body["error"]["code"] == 3
    assert "no agent named" in body["error"]["message"]
