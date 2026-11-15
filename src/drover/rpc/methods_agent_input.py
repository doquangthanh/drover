"""RPC methods for driving an agent's UI: prompt (and wait), named keys, waiting for output text."""

from __future__ import annotations

import asyncio
import re
import time

from drover.core.terminal_key_names import encode_keys
from drover.rpc.methods_panes import TERMINAL_STATES, _pane, gate_agent_input, mark_busy, wait_for_state
from drover.rpc.rpc_registry import (
    E_BAD_PARAMS,
    E_BLOCKED,
    E_GENERAL,
    E_STALLED,
    E_TIMEOUT,
    RpcError,
    need,
    registry,
)

STALL_SECONDS = 5.0  # a prompt that shows no sign of work this long after Enter has "stalled"
PASTE_ENTER_DELAY = 0.05  # let the app finish taking the paste before Enter arrives
OUTPUT_POLL = 0.25


BLOCKED_MESSAGE = ("agent_blocked: the agent is waiting on a question or permission prompt; nothing was sent. "
                   "Read it with `dr read`; the user answers permission prompts")


async def _submit(pane, text: str) -> float:
    """Type the prompt (as a bracketed paste when the app asked for it), then Enter.

    Returns the moment just before Enter: the echo of the typed text came before it, so it is not mistaken for work.
    """
    if pane.modes.bracketed_paste:
        pane.write("\x1b[200~" + text.replace("\x1b[201~", "") + "\x1b[201~")  # the text cannot end the paste
    else:
        pane.write(text)
    await asyncio.sleep(PASTE_ENTER_DELAY)
    pane.flush_screen()
    if pane.state == "blocked":  # a dialog opened while we typed: never let our Enter answer it
        raise RpcError(E_BLOCKED, BLOCKED_MESSAGE.replace("nothing was sent", "the text was typed but not submitted"))
    enter_at = time.time()
    pane.write("\r")
    return enter_at


async def _await_activity(pane, since: float, timeout: float) -> None:
    """Wait until the agent looks busy (or asks something) after `since`; raise if it never does.

    Busy also needs the screen to have changed since: the activity fallback would otherwise count start-up output,
    or the terminal queries ConPTY emits on first input, as work.
    """
    deadline = time.monotonic() + min(STALL_SECONDS, timeout)
    while time.monotonic() < deadline:
        busy = pane.tracker.detected_working_at >= since and pane.screen_changed_at >= since
        if busy or pane.state in ("blocked", "exited"):
            return
        await asyncio.sleep(0.1)
    if timeout <= STALL_SECONDS:
        raise RpcError(E_TIMEOUT, f"timed out after {timeout:.0f}s; state is {pane.state}")
    raise RpcError(E_STALLED, "agent_prompt_stalled: prompt sent but the agent did not start working; "
                              "`dr read` it before retrying so the prompt is not sent twice")


@registry.method("pane.prompt", "Submit a prompt to an agent; refuses one on a permission prompt",
                 "pane, text, wait?, states?, timeout?, caller?")
async def pane_prompt(ctx, p: dict) -> dict:
    pane_id = _pane(ctx, p)
    pane = ctx.manager.get(pane_id)
    text = need(p, "text")
    t0 = time.monotonic()
    timeout = float(p.get("timeout", 600))
    async with pane.input_lock:  # a second prompt must not land between this one's text and its Enter
        if pane.state == "blocked":
            raise RpcError(E_BLOCKED, BLOCKED_MESSAGE)
        if pane.state in ("exited", "stopped"):
            raise RpcError(E_GENERAL, f"agent is {pane.state}")
        started_at = await _submit(pane, text)
        mark_busy(ctx, pane)
    if p.get("caller"):
        ctx.manager.messages.add("send", p["caller"], pane_id, text)
    if not p.get("wait"):
        return {"pane": pane_id, "state": pane.state}
    await _await_activity(pane, started_at, timeout)
    wanted = set(p.get("states") or ["done", "idle", "blocked"]) | TERMINAL_STATES
    remaining = timeout - (time.monotonic() - t0)
    # mark_busy forced "working", so idle/done now really means this turn settled.
    state = await wait_for_state(ctx, pane, wanted, remaining, accept_current=True)
    return {"pane": pane_id, "state": state}


@registry.method("pane.keys", "Press named keys in a pane (esc, enter, up, ctrl+c, shift+tab...)",
                 "pane, keys: [names], caller?")
async def pane_keys(ctx, p: dict) -> dict:
    pane_id = _pane(ctx, p)
    pane = ctx.manager.get(pane_id)
    names = p.get("keys")
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise RpcError(E_BAD_PARAMS, "keys must be a list of key names")
    data = encode_keys(names)
    label = " ".join(names)
    gate_agent_input(ctx, pane_id, pane, data, f"[keys] {label}", p.get("caller"))
    pane.write(data)
    if p.get("caller"):
        ctx.manager.messages.add("keys", p["caller"], pane_id, label)
    return {"pane": pane_id, "keys": names}


def _matcher(pattern: str, regex: bool):
    if not regex:
        return lambda line: pattern in line
    try:
        compiled = re.compile(pattern)
    except re.error as exc:
        raise RpcError(E_BAD_PARAMS, f"bad regex: {exc}") from exc
    return lambda line: compiled.search(line) is not None


@registry.method("pane.wait_output", "Block until text (or a regex) shows in a pane's recent output",
                 "pane, pattern, regex?, lines?, timeout?")
async def pane_wait_output(ctx, p: dict) -> dict:
    pane_id = _pane(ctx, p)
    pane = ctx.manager.get(pane_id)
    match = _matcher(need(p, "pattern"), bool(p.get("regex")))
    lines = max(1, int(p.get("lines") or 80))
    timeout = float(p.get("timeout", 600))
    if p.get("caller"):
        ctx.manager.messages.add("wait", p["caller"], pane_id, f"output {p['pattern']!r}")
    deadline = time.monotonic() + timeout
    while True:
        pane.flush_screen()
        recent = pane.screen.all_lines()[-lines:]
        hit = next((line for line in reversed(recent) if match(line)), None)
        if hit is not None:
            return {"pane": pane_id, "matched_line": hit, "text": "\n".join(recent)}
        if pane_id not in ctx.manager.panes:
            raise RpcError(E_GENERAL, "pane was closed before the output appeared")
        if not pane.alive and not pane._pending_screen and time.time() - pane.last_output_at > 1:
            # Exited, and its last output (already flushed above) did not match.
            raise RpcError(E_GENERAL, f"pane exited before the output appeared (state {pane.state})")
        if time.monotonic() >= deadline:
            raise RpcError(E_TIMEOUT, f"timed out after {timeout:.0f}s waiting for {p['pattern']!r}")
        await asyncio.sleep(OUTPUT_POLL)
