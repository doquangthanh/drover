"""Read more than one screen from a full-screen agent (OpenCode, Claude in fullscreen mode).

Such apps draw their transcript on the alternate screen, so the pane has no scrollback. When the app reports
SGR mouse input, we scroll its own viewport with wheel events, collect overlapping pages, then scroll back down.
Only used for idle/done agents: scrolling a working agent would fight its redraws.
"""

from __future__ import annotations

import asyncio

WHEEL_UP, WHEEL_DOWN = 64, 65
NOTCHES_PER_PAGE = 5
PAGE_SETTLE = 0.25  # seconds for the app to redraw after a scroll
MAX_PAGES = 40


def merge_pages(older: list[str], newer: list[str]) -> list[str]:
    """Join a page scrolled further up (`older`) onto what we have (`newer`) using their largest overlap."""
    for size in range(min(len(older), len(newer)), 0, -1):
        if older[-size:] == newer[:size] and any(line.strip() for line in older[-size:]):
            return older + newer[size:]
    return older + newer


def fixed_chrome(first: list[str], scrolled: list[str]) -> tuple[int, int]:
    """Rows that did not move when the transcript scrolled: a header and a footer (input box, status bar)."""
    limit = min(len(first), len(scrolled)) - 1
    top = 0
    while top < limit and first[top] == scrolled[top]:
        top += 1
    bottom = 0
    while bottom < limit - top and first[-1 - bottom] == scrolled[-1 - bottom]:
        bottom += 1
    return top, bottom


def _wheel(button: int, cols: int, rows: int, notches: int) -> str:
    return f"\x1b[<{button};{max(1, cols // 2)};{max(1, rows // 2)}M" * notches


async def _scroll(pane, button: int, notches: int) -> list[str]:
    pane.write(_wheel(button, pane.cols, pane.rows, notches))
    await asyncio.sleep(PAGE_SETTLE)
    pane.flush_screen()
    return pane.screen.visible_lines()


async def read_scrolled_history(pane, wanted_lines: int) -> list[str]:
    """Scroll `pane` up until `wanted_lines` are collected or the top stops moving, then return to the bottom.

    Header/footer rows that stay put while scrolling are kept once (footer at the end), not once per page.
    """
    pane.flush_screen()
    first = previous = pane.screen.visible_lines()
    top = bottom = 0
    measured = False
    body: list[str] = []
    up_notches = 0
    try:
        for _ in range(MAX_PAGES):
            page = await _scroll(pane, WHEEL_UP, NOTCHES_PER_PAGE)
            up_notches += NOTCHES_PER_PAGE
            if page == previous:  # reached the top of the transcript
                break
            if not measured:
                top, bottom = fixed_chrome(first, page)
                body, measured = first[top:len(first) - bottom], True
            body = merge_pages(page[top:len(page) - bottom], body)
            previous = page
            if len(body) + bottom >= wanted_lines:
                break
    finally:
        if up_notches:
            await _scroll(pane, WHEEL_DOWN, up_notches + NOTCHES_PER_PAGE)
    lines = body + first[len(first) - bottom:] if measured else list(first)
    while lines and not lines[-1]:
        lines.pop()
    return lines[-wanted_lines:]
