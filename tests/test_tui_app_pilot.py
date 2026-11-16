"""TuiApp headless (Textual Pilot) against a real daemon: sidebar, layout, prefix keys, responsive, restore dialog."""

from __future__ import annotations

import asyncio

from drover.tui.daemon_ws_connection import DaemonConnection
from drover.tui.restore_stopped_dialog import RestoreStoppedDialog
from drover.tui.split_layout_view import SplitLayoutView
from drover.tui.tab_bar import TabBar
from drover.tui.tui_app import TuiApp
from drover.tui.workspace_sidebar import WorkspaceSidebar


async def until(predicate, timeout: float = 15.0):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        assert asyncio.get_running_loop().time() < deadline, "condition not reached"
        await asyncio.sleep(0.05)


def make_app(daemon) -> TuiApp:
    return TuiApp(DaemonConnection(str(daemon.client.make_url("/")), daemon.token))


def sidebar_labels(app: TuiApp) -> str:
    return app.query_one(WorkspaceSidebar).labels()


def tabbar_text(app: TuiApp) -> str:
    return app.query_one(TabBar).plain


async def test_sidebar_lists_spaces_and_new_panes(start_daemon, tmp_path):
    daemon = await start_daemon()
    await daemon.call("space.create", {"cwd": str(tmp_path)})
    app = make_app(daemon)
    async with app.run_test(size=(120, 40)) as pilot:
        await until(lambda: tmp_path.name in sidebar_labels(app))
        await daemon.call("pane.create", {"command": "", "cwd": str(tmp_path), "name": "second-shell"})
        await until(lambda: "second-shell" in tabbar_text(app))  # a new tab of the same space
        assert app.query_one("#root").has_class("-wide")
        await pilot.pause()


async def test_split_typing_zoom_and_responsive(start_daemon, tmp_path):
    daemon = await start_daemon()
    await daemon.call("space.create", {"cwd": str(tmp_path)})
    _, panes = await daemon.call("pane.list")
    first = panes["result"][0]["id"]
    await daemon.call("pane.split", {"pane": first, "direction": "right"})
    app = make_app(daemon)
    async with app.run_test(size=(120, 40)) as pilot:
        layout = app.query_one(SplitLayoutView)
        await until(lambda: len(layout.views) == 2)
        await until(lambda: len({v.region.x for v in layout.views.values()}) == 2)  # side by side
        await until(lambda: app.focused_pane in layout.views)
        await pilot.press(*["echo", "hi-from-tui"][0], "space", *"hi-from-tui", "enter")
        focused = app.focused_pane
        await until(lambda: "hi-from-tui" in "".join(
            "".join(t for t, _ in layout.views[focused].emulator.row_runs(y))
            for y in range(layout.views[focused].emulator.rows)))
        # responsive: medium hides the docked sidebar, narrow shows one pane
        await pilot.resize_terminal(80, 30)
        await pilot.pause()
        assert not app.query_one("#root").has_class("-wide") and len(layout.views) == 2
        await pilot.resize_terminal(50, 30)
        await until(lambda: len(layout.views) == 1)
        await pilot.resize_terminal(120, 40)
        await until(lambda: len(layout.views) == 2 and app.query_one("#root").has_class("-wide"))
        # zoom via prefix
        await pilot.press("ctrl+b", "z")
        await until(lambda: len(layout.views) == 1)
        await pilot.press("ctrl+b", "z")
        await until(lambda: len(layout.views) == 2)
        # split right via prefix
        await pilot.press("ctrl+b", "percent_sign")
        await until(lambda: len(layout.views) == 3)


async def test_restore_dialog_discards_only_ticked_and_asks_once(start_daemon, tmp_path):
    first = await start_daemon()
    await first.call("space.create", {"cwd": str(tmp_path)})
    _, panes = await first.call("pane.list")
    await first.call("pane.split", {"pane": panes["result"][0]["id"], "direction": "right"})
    first.ctx.persistence.save_now()
    daemon = await start_daemon()  # "restart": loads the saved session, its panes come back as stopped
    assert len(daemon.ctx.manager.stopped) == 2
    app = make_app(daemon)
    async with app.run_test(size=(120, 40)) as pilot:
        await until(lambda: isinstance(app.screen, RestoreStoppedDialog))
        await pilot.press("space")  # untick the highlighted one
        await pilot.press("d")  # discard the ticked one
        await until(lambda: len(daemon.ctx.manager.stopped) == 1)
        await until(lambda: not isinstance(app.screen, RestoreStoppedDialog))
        app.schedule_refresh()
        await pilot.pause(0.5)
        assert not isinstance(app.screen, RestoreStoppedDialog)  # the remaining one was already asked about


async def test_pane_size_reaches_daemon_and_zoom_detaches_hidden_pane(start_daemon, tmp_path):
    daemon = await start_daemon()
    await daemon.call("space.create", {"cwd": str(tmp_path)})
    _, panes = await daemon.call("pane.list")
    await daemon.call("pane.split", {"pane": panes["result"][0]["id"], "direction": "right"})
    app = make_app(daemon)
    async with app.run_test(size=(120, 40)) as pilot:
        layout = app.query_one(SplitLayoutView)
        await until(lambda: len(layout.views) == 2)

        def listeners() -> int:
            return sum(len(p.output_listeners) for p in daemon.ctx.manager.panes.values())

        await until(lambda: listeners() == 2)
        sizes = {pid: (v.size.width, v.size.height) for pid, v in layout.views.items()}
        await until(lambda: all((p.cols, p.rows) == sizes[pid] for pid, p in daemon.ctx.manager.panes.items()))
        await pilot.press("ctrl+b", "z")
        await until(lambda: len(layout.views) == 1 and listeners() == 1)  # the hidden pane was detached


async def test_sidebar_enter_switches_tab_and_literal_prefix(start_daemon, tmp_path):
    daemon = await start_daemon()
    await daemon.call("space.create", {"cwd": str(tmp_path)})
    await daemon.call("pane.create", {"command": "", "cwd": str(tmp_path), "name": "other-tab"})  # new tab
    app = make_app(daemon)
    async with app.run_test(size=(120, 40)) as pilot:
        layout = app.query_one(SplitLayoutView)
        await until(lambda: len(app.state["tabs"]) == 2 and layout.tab_id)
        first = layout.tab_id
        await pilot.press("ctrl+b", "tab")  # next tab
        await until(lambda: layout.tab_id not in (None, first))
        await pilot.press("ctrl+b", "1")  # back to tab 1
        await until(lambda: layout.tab_id == app.state["tabs"][0]["id"])
        await pilot.press("ctrl+b", "b")  # focus the sidebar
        await until(lambda: app.query_one("#spaces").has_focus)
        await pilot.press("ctrl+b", "d")  # quit


async def test_empty_session_opens_a_space_and_herdr_keys(start_daemon, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    daemon = await start_daemon()
    app = make_app(daemon)
    async with app.run_test(size=(120, 40)) as pilot:
        await until(lambda: len(app.state["spaces"]) == 1 and app.focused_pane)  # opened by itself, like herdr
        assert app.state["spaces"][0]["cwd"] == str(tmp_path.resolve())
        await pilot.press("ctrl+b", "c")  # new tab in this space
        await until(lambda: len(app.state["tabs"]) == 2 and app.current_tab_id == app.state["tabs"][1]["id"])
        await pilot.press("ctrl+b", "p")  # previous tab
        await until(lambda: app.current_tab_id == app.state["tabs"][0]["id"])
        await pilot.press("ctrl+b", "v")  # split right
        layout = app.query_one(SplitLayoutView)
        await until(lambda: len(layout.views) == 2)
        await pilot.press("ctrl+b", "N")  # new space
        await until(lambda: len(app.state["spaces"]) == 2)
        await until(lambda: app.current_space_id() == app.state["spaces"][1]["id"])
        await pilot.press("ctrl+b", "W")  # rename space
        await pilot.pause(0.2)
        await pilot.press("ctrl+u", *"proj", "enter")
        await until(lambda: any(s["name"] == "proj" for s in app.state["spaces"]))
        await pilot.press("ctrl+b", "g")  # goto picker
        await pilot.pause(0.2)
        await pilot.press("escape")
        await pilot.press("ctrl+b", "q")  # detach
