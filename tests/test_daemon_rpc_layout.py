"""Daemon RPC: tab.create, pane.split/move/swap/zoom/share and unique agent names, on real panes."""

from __future__ import annotations

from pathlib import Path

from drover.core import split_layout_tree as layout


async def _pane(daemon, cwd: Path, name: str) -> dict:
    _, created = await daemon.call("pane.create", {"command": "cmd /k", "cwd": str(cwd), "name": name})
    return created["result"]


def _tab(daemon, tab_id: str):
    return daemon.ctx.manager.tabs[tab_id]


async def test_split_returns_the_new_pane_beside_the_target(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    first = await _pane(daemon, drover_dirs, "lead")
    _, body = await daemon.call("pane.split", {"pane": "lead", "direction": "down", "name": "helper"})
    new = body["result"]["pane"]
    assert new["tab_id"] == first["tab_id"] and new["name"] == "helper"
    tree = _tab(daemon, first["tab_id"]).layout
    assert tree["split"] == "col" and layout.pane_ids(tree) == [first["id"], new["id"]]


async def test_split_rejects_an_unknown_direction(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    await _pane(daemon, drover_dirs, "lead")
    _, body = await daemon.call("pane.split", {"pane": "lead", "direction": "sideways"})
    assert body["error"]["code"] == 5


async def test_tab_create_opens_a_new_tab_in_the_space(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    first = await _pane(daemon, drover_dirs, "lead")
    _, body = await daemon.call("tab.create", {"space": first["space_id"], "name": "logs"})
    result = body["result"]
    assert result["tab"]["id"] != first["tab_id"]
    assert result["tab"]["name"] == "logs" and result["pane"]["tab_id"] == result["tab"]["id"]
    assert result["tab"]["layout"] == {"pane": result["pane"]["id"]}


async def test_move_to_a_new_tab_drops_the_emptied_tab(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    first = await _pane(daemon, drover_dirs, "lead")
    _, body = await daemon.call("pane.move", {"pane": first["id"], "new_tab": True})
    result = body["result"]
    assert result["previous_tab"] == first["tab_id"]
    assert result["pane"]["tab_id"] == result["tab"]["id"] != first["tab_id"]
    assert first["tab_id"] not in daemon.ctx.manager.tabs


async def test_move_into_another_tab_splits_it(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    a = await _pane(daemon, drover_dirs, "a")
    b = await _pane(daemon, drover_dirs, "b")
    _, body = await daemon.call("pane.move", {"pane": "b", "tab": a["tab_id"]})
    assert body["result"]["tab"]["id"] == a["tab_id"]
    assert layout.pane_ids(_tab(daemon, a["tab_id"]).layout) == [a["id"], b["id"]]
    _, again = await daemon.call("pane.move", {"pane": "b", "tab": a["tab_id"]})
    assert again["error"]["code"] == 5


async def test_move_with_a_bad_direction_changes_nothing(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    a = await _pane(daemon, drover_dirs, "a")
    tabs_before = set(daemon.ctx.manager.tabs)
    for params in ({"pane": "a", "new_tab": True, "direction": "left"}, {"pane": "a", "tab": "t999"}):
        _, body = await daemon.call("pane.move", params)
        assert "error" in body
    assert set(daemon.ctx.manager.tabs) == tabs_before
    assert _tab(daemon, a["tab_id"]).layout == {"pane": a["id"]}


def test_foreign_ids_flags_ids_of_another_machine():
    from drover.remote.id_prefixing import foreign_ids, route_of

    assert route_of({"tab": "vps:t2", "name": "x"}) == "vps:t2"
    assert foreign_ids({"pane": "vps:%3", "target": "vps:%4"}, "vps") == []
    assert foreign_ids({"pane": "vps:%3", "target": "%2"}, "vps") == ["target=%2"]


async def test_swap_across_tabs_exchanges_places(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    a = await _pane(daemon, drover_dirs, "a")
    b = await _pane(daemon, drover_dirs, "b")
    _, body = await daemon.call("pane.swap", {"pane": "a", "target": "b"})
    swapped = {p["name"]: p["tab_id"] for p in body["result"]["panes"]}
    assert swapped == {"a": b["tab_id"], "b": a["tab_id"]}
    assert _tab(daemon, a["tab_id"]).layout == {"pane": b["id"]}
    _, same = await daemon.call("pane.swap", {"pane": "a", "target": "a"})
    assert same["error"]["code"] == 5


async def test_zoom_and_share_change_the_tab(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    a = await _pane(daemon, drover_dirs, "a")
    await daemon.call("pane.split", {"pane": "a", "name": "b"})
    _, zoomed = await daemon.call("pane.zoom", {"pane": "a"})
    assert zoomed["result"]["tab"]["zoomed"] is True and zoomed["result"]["tab"]["focused"] == a["id"]
    _, share = await daemon.call("pane.share", {"pane": "b", "share": 0.7})
    assert abs(share["result"]["tab"]["layout"]["ratio"] - 0.3) < 1e-9  # b is the second half
    _, bad = await daemon.call("pane.share", {"pane": "b", "share": 2})
    assert bad["error"]["code"] == 5


async def test_rename_gives_a_unique_name_usable_as_a_target(start_daemon, drover_dirs: Path):
    daemon = await start_daemon()
    a = await _pane(daemon, drover_dirs, "a")
    await _pane(daemon, drover_dirs, "b")
    _, body = await daemon.call("pane.rename", {"pane": a["id"], "name": "reviewer"})
    assert body["result"] == {"pane": a["id"], "name": "reviewer"}
    _, read = await daemon.call("pane.read", {"pane": "reviewer"})
    assert read["result"]["pane"] == a["id"]
    _, clash = await daemon.call("pane.rename", {"pane": "b", "name": "reviewer"})
    assert clash["error"]["code"] == 5 and "already used" in clash["error"]["message"]
    _, bad = await daemon.call("pane.rename", {"pane": "b", "name": "x/y"})
    assert bad["error"]["code"] == 5
