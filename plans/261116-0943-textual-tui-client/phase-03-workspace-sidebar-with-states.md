# Phase 03 — Sidebar: spaces > tabs > agents with state

## Context links
- `src/drover/core/session_manager.py` `snapshot()` (spaces, tabs, panes, stopped), `daemon_context.combined_state()` (+machines, prefix, theme)
- `src/drover/status/status_change_tracker.py` (public states: working | blocked | idle | done | exited | stopped)
- `src/drover/core/workspace_models.py` (Space, Tab with `layout`, `focused`, `zoomed`)
- Web reference: `frontend/src/core/store-derive.ts`

## Overview
Priority P1. Status done (automated checks; manual checks not run). Read-only tree + selection that drives the body.

## Key insights
- Pane dict has `space_id`, `tab_id`, `state`, `unread`, `name`, `title`, `parent` (verified `PaneSession.to_dict`).
- Stopped panes live in `state["stopped"]` with `tab_id`, still in the tab layout (verified `load_previous`).
- Remote machine panes come prefixed `alias:` in combined state — show them, but no special UI now (YAGNI).

## Requirements
- Tree: Space (name) > Tab (name, badge = worst state of its panes) > Pane (glyph + name).
- State glyph + colour from terminal theme (ANSI names, so the user's terminal palette is used):
  working `●` yellow, blocked `!` red bold, done `✓` green, idle `○` dim, exited/stopped `×` dim.
- Select tab -> body shows that tab; select pane -> focus it (and its tab). Enter/click both work.
- Updates keep expansion + cursor position (no full rebuild flicker).

## Architecture
```
tui_state_helpers.py (pure):  tabs_of(space), panes_of(tab), worst_state(states), state_glyph(state),
                              tab_of_pane(pane_id), stopped_in_tab(tab)
WorkspaceSidebar(Tree)  rebuild(state) -> diff by node id (s1/t2/%3) ; posts TabSelected / PaneSelected
```
Use Textual `Tree` widget (built-in). Node `data` = id.

## Related code files
Create:
- `src/drover/tui/tui_state_helpers.py`
- `src/drover/tui/workspace_sidebar.py`
- `tests/test_tui_state_helpers.py`, `tests/test_tui_workspace_sidebar_pilot.py`
Modify:
- `src/drover/tui/tui_app.py` (compose sidebar, handle selection messages, track `current_tab`)
- `src/drover/tui/tui_messages.py` (TabSelected, PaneSelected)

## Implementation steps
1. Pure helpers + tests (state priority: blocked > done > working > idle > exited/stopped).
2. Sidebar: build once; on state update, update labels in place, add/remove changed nodes only.
3. Throttle refresh: coalesce state/status events into one update per 100 ms (`set_timer`).
4. Default selection on start: tab of the last focused pane, else first tab.
5. On `PaneSelected` call `rpc("pane.focus", {pane})` (marks read, clears `done`, verified in session_manager focus code).

## Todo
- [ ] tui_state_helpers.py + tests
- [ ] workspace_sidebar.py
- [ ] app wiring + throttle
- [ ] Pilot test

## Success criteria (how checked)
- `pytest -q tests/test_tui_state_helpers.py`: worst_state and glyph table cases.
- `pytest -q tests/test_tui_workspace_sidebar_pilot.py`: real daemon (harness) with 2 spaces / 2 shells; `app.run_test(size=(100,30))`;
  assert tree labels contain space names and pane names; create a third pane via rpc -> it appears within 1 s; press Down+Enter -> `app.current_tab` changes.
- Manual: `dr tui` next to the web UI — states match (working while command runs, idle after).

## Risks
- Tree rebuild resets cursor -> mitigated by in-place label updates.
- Unicode glyph width in some terminals -> keep one-cell glyphs; fallback ASCII set if `TERM=linux` (only if seen in practice).

## Security
Read-only; no new data exposed.

## Next steps
Phase 04 renders the selected tab's layout.
