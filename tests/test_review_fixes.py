"""Regression tests for the code-review findings (H1, H4, M5, L1)."""

from __future__ import annotations

import asyncio
import time

import pytest

from herd.core.event_hub import BoundedQueue
from herd.remote.machine_registry import validate_new
from herd.status.status_change_tracker import StatusTracker


def test_tracker_hold_keeps_working_after_new_input():
    """H1: right after `hd send`, an idle screen must not flip the pane back to done/idle."""
    t = StatusTracker(state="working", since=time.time())
    t.hold_until = time.time() + 3
    now = time.time()
    assert t.observe("idle", 0, focused=False, now=now) is None
    assert t.observe("idle", 0, focused=False, now=now + 1) is None
    assert t.state == "working"


def test_tracker_done_after_hold_expires():
    start = time.time()
    t = StatusTracker(state="working", since=start)
    t.hold_until = start + 1
    assert t.observe("idle", 0, focused=False, now=start + 2) is None  # candidate
    assert t.observe("idle", 0, focused=False, now=start + 2.6) == "done"


async def test_bounded_queue_never_drops_rpc_replies():
    """M5: on overflow, output is dropped and a resync is queued, but every reply survives."""
    q = BoundedQueue(maxsize=5)
    q.put({"t": "res", "id": 1})
    for i in range(20):
        q.put({"t": "out", "pane": "%1", "data": str(i)})
    q.put({"t": "res", "id": 2})
    items = [await asyncio.wait_for(q.get(), 1) for _ in range(len(q.items))]
    kinds = [i["t"] for i in items]
    assert [i["id"] for i in items if i["t"] == "res"] == [1, 2]
    assert "resync" in kinds


@pytest.mark.parametrize("alias", ["s1", "t3", "a12"])
def test_machine_alias_cannot_look_like_internal_id(alias):
    """L1: aliases like t3 would collide with tab ids in the combined view."""
    with pytest.raises(ValueError):
        validate_new(alias, "me@host", {})
