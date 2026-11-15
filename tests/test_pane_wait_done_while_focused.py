"""`dr wait --state done` returns when a focused agent finishes (working -> idle, no "done" badge) instead of hanging."""

import asyncio
from types import SimpleNamespace

from drover.core.event_hub import EventHub
from drover.rpc.methods_panes import wait_for_state


def _setup():
    ctx = SimpleNamespace(hub=EventHub())
    pane = SimpleNamespace(meta=SimpleNamespace(id="%1"), state="working")
    return ctx, pane


def _status(ctx, old, new):
    ctx.hub.emit("status", {"pane": {"id": "%1"}, "old": old, "new": new})


async def test_focused_finish_counts_as_done():
    ctx, pane = _setup()
    task = asyncio.create_task(wait_for_state(ctx, pane, {"done", "exited"}, 2))
    await asyncio.sleep(0)
    _status(ctx, "working", "idle")
    assert await task == "idle"


async def test_acknowledged_done_does_not_count_twice():
    ctx, pane = _setup()
    task = asyncio.create_task(wait_for_state(ctx, pane, {"done", "exited"}, 0.3))
    await asyncio.sleep(0)
    _status(ctx, "done", "idle")  # user looked at an already finished pane: not a new turn ending
    try:
        await task
        raise AssertionError("should time out")
    except Exception as exc:  # noqa: BLE001 - RpcError timeout
        assert "timed out" in str(exc)
