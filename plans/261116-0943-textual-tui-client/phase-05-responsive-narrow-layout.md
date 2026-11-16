# Phase 05 — Responsive layout for narrow / short terminals

## Context links
- `frontend/src/styles/mobile.css`, `frontend/src/core/viewport.ts` (web phone behaviour, for reference only)
- Phase 04 `split_layout_view.py`

## Overview
Priority P2. Status done (automated checks; manual checks not run). Textual already handles SIGWINCH and posts `Resize` events (Textual docs; guessed detail: event fires on app/screen) — we only decide the layout per size.

## Key insights
- Each pane PTY has one size; shrinking the TUI resizes agents (affects web viewers too). Debounce resize RPCs (150 ms, phase 01).
- `pane.resize` clamps to cols>=10, rows>=3 (verified `PaneSession.resize`) — never send smaller; show "too small" instead.

## Requirements (breakpoints, cells)
| Width | Sidebar | Panes |
|---|---|---|
| >= 100 | shown (24-30 cols) | full split tree |
| 60-99 | hidden; `C-a b` overlays it | full split tree |
| < 60 or height < 15 | hidden overlay | focused pane only (auto-zoom view, client side, no `tab.zoom` rpc); `C-a o` cycles panes |
- Overlay sidebar closes after a selection.
- Status line shows tab name + "k/n panes" when auto-zoomed so hidden panes are not forgotten (with worst state glyph).

## Architecture
```
responsive_mode.py (pure): mode_for(width, height) -> "wide" | "medium" | "narrow"
TuiApp.on_resize -> mode change? -> toggle sidebar class / SplitLayoutView.set_single_pane(bool)
```
Use Textual CSS classes (`-narrow`, `-medium`) on the App/Screen + small TCSS file for sidebar dock/overlay.

## Related code files
Create:
- `src/drover/tui/responsive_mode.py`
- `src/drover/tui/tui_app.tcss` (layout styles; Textual `CSS_PATH`)
- `tests/test_tui_responsive_layout_pilot.py`
Modify:
- `src/drover/tui/tui_app.py`, `src/drover/tui/split_layout_view.py` (single-pane flag reuses zoom path), `src/drover/tui/workspace_sidebar.py` (overlay mode)

## Implementation steps
1. Pure `mode_for` + table test.
2. CSS classes for sidebar docked vs overlay (layer) vs hidden.
3. `set_single_pane(True)` = same code path as zoom (DRY), keeps attach/detach diff.
4. Status line counter.

## Todo
- [ ] responsive_mode.py + test
- [ ] tcss + class toggling
- [ ] single-pane mode via zoom path
- [ ] Pilot resize test

## Success criteria (how checked)
- `pytest -q tests/test_tui_responsive_layout_pilot.py`: `run_test(size=(120,40))` sidebar visible and 2 panes;
  `await pilot.resize_terminal(80, 30)` -> sidebar hidden, 2 panes; `(50, 30)` -> 1 pane, status shows "1/2"; back to `(120,40)` -> restored.
  (If `pilot.resize_terminal` is missing in the installed Textual, start separate `run_test` with each size.)
- Daemon side: after resize settles, `pane.list` cols/rows equal the widget content size (assert in same test).
- Manual: drag terminal window narrow/wide; phone-sized terminal (e.g. Termux over ssh) if available.

## Risks
- Resize storms while dragging -> debounce; only last size is sent.
- Web UI open at the same time fights sizes -> documented limitation (no daemon change).

## Security
None new.

## Next steps
Phase 06 restore dialog.
