"""pane.wait_children: `dr wait --children all|any`, a parent waiting on the helpers it started (Herdr-style)."""

from __future__ import annotations

import asyncio
import contextlib
import time

from drover.rpc.rpc_registry import E_BAD_PARAMS, E_TIMEOUT, RpcError, registry

BOOT_GRACE = 5.0  # a helper started this recently counts as working: its task may not have reached it yet
NEWS_STATES = ("done", "blocked", "exited")


@registry.method("pane.wait_children", "Block until the caller's helpers stop working (all) or one has news (any)",
                 "caller, mode?: all|any, timeout?")
async def pane_wait_children(ctx, p: dict) -> dict:
    caller, mode, m = p.get("caller"), p.get("mode", "all"), ctx.manager
    if caller not in m.panes:
        raise RpcError(E_BAD_PARAMS, "wait --children only works inside a drover pane (DR_PANE_ID)")
    if mode not in ("all", "any"):
        raise RpcError(E_BAD_PARAMS, "mode must be 'all' or 'any'")
    timeout = float(p.get("timeout", 600))

    def kids():
        return [m.panes[c] for c in m.children_of(caller) if c in m.panes]

    def busy(k) -> bool:
        return k.state == "working" or (k.state == "idle" and time.time() - k.meta.created_at < BOOT_GRACE)

    def reply(reason: str, **extra) -> dict:
        children = [{"pane": k.meta.id, "name": k.meta.name, "state": k.state} for k in kids()]
        m.notes.drop(caller, [extra["pane"]] if "pane" in extra else [c["pane"] for c in children])
        return {"reason": reason, **extra, "children": children}

    if not kids():
        return reply("no_children")
    if not any(busy(k) for k in kids()):
        return reply("all" if mode == "all" else "none_working")
    news: list[tuple[str, str]] = []
    changed = asyncio.Event()

    def listener(name, data):
        if name != "status" or data["pane"].get("parent") != caller:
            return
        finished = data["old"] == "working" and data["new"] == "idle"
        if data["new"] in NEWS_STATES or finished:
            news.append((data["pane"]["id"], "done" if finished else data["new"]))
        changed.set()

    m.messages.add("wait", caller, None, f"children:{mode}")
    unsubscribe = ctx.hub.subscribe(listener)
    deadline = time.monotonic() + max(0.0, timeout)
    try:
        with m.notes.waiting(caller):
            while True:
                if mode == "any" and news:
                    return reply("child", pane=news[0][0], state=news[0][1])
                if mode == "all" and not any(busy(k) for k in kids()):
                    return reply("all")
                left = deadline - time.monotonic()
                if left <= 0:
                    states = ", ".join(f"{k.meta.name} {k.state}" for k in kids())
                    raise RpcError(E_TIMEOUT, f"timed out after {timeout:.0f}s; helpers: {states}")
                changed.clear()
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(changed.wait(), min(left, 0.5))  # also re-checks the boot grace
    finally:
        unsubscribe()
