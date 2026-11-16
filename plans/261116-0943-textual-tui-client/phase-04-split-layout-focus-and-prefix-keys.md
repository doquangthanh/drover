# Phase 04 — Split layout, pane focus, keyboard input, prefix keys

## Context links
- `src/drover/core/split_layout_tree.py` (node shapes `{pane}` / `{split: row|col, ratio, a, b}`; `row` = side by side)
- `src/drover/rpc/methods_workspace.py` / `methods_layout.py` (`tab.zoom`, `pane.split`, `pane.close`)
- `frontend/src/core/keys.ts` (prefix default `C-a`, shortcut table — mirror keys, not all actions)
- `combined_state()["prefix"]` (setting, default `"C-a"`, verified)

## Overview
Priority P1. Status pending. Render a tab's layout tree as nested containers; each leaf is a `TerminalPaneView`; keys go to the focused pane except after the prefix.

## Key insights
- Tree is binary with `ratio` -> map to Textual `Horizontal`/`Vertical` with child sizes `fr` = ratio / 1-ratio.
- Stopped panes are still leaves in the layout (verified) -> render a placeholder `StoppedPaneView` (name + "stopped — prefix r to restore").
- `tab.zoomed` + `tab.focused` (verified Tab model) -> zoomed = render only the focused leaf.
- Every visible live leaf is attached (`attach`), detached when it leaves the screen; each sends `pane.resize` for its own box size.

## Requirements
- Layout rebuild only when `tab.layout`/`zoomed`/current tab changes (compare JSON), not on every status event.
- Focus: highlighted border on focused pane; title bar = name + state glyph.
- Prefix (from state, default Ctrl+A; second press sends the literal Ctrl+A to the pane). Minimum key set:
  `o`/arrows focus next/neighbour, `z` zoom (`tab.zoom`), `%` / `"` split right/down (`pane.split`), `x` close (`pane.close`, confirm),
  `n` next blocked, `Tab`/`p` next/prev tab, `1-9` go to tab, `b` toggle sidebar, `r` restore/restart, `d` quit TUI (detach — agents keep running), `?` help.
- Everything else -> focused pane bytes (phase 01 mapping).

## Architecture
```
split_layout_view.py
  build_layout_widgets(node, panes, stopped) -> Widget   (recursive; pure mapping helper tested apart)
  SplitLayoutView(Container).show_tab(tab, state)        (rebuild on signature change; attach/detach diff)
prefix_key_router.py
  PrefixKeyRouter: armed flag + timeout 2 s; handle(key) -> action name | None ; table KEY -> action
tui_app.py
  on_key (priority) -> router; actions call conn.rpc(...)
```
Focus neighbours: use widget regions (`region.center`) to pick nearest pane in a direction — no tree math.

## Related code files
Create:
- `src/drover/tui/split_layout_view.py`
- `src/drover/tui/stopped_pane_view.py` (tiny Static subclass; may live in split_layout_view if <200 lines total)
- `src/drover/tui/prefix_key_router.py`
- `src/drover/tui/tui_actions.py` (action name -> rpc/app call; keeps tui_app.py <200 lines)
- `tests/test_tui_split_layout_view_pilot.py`, `tests/test_tui_prefix_key_router.py`
Modify:
- `src/drover/tui/tui_app.py`, `src/drover/tui/terminal_pane_view.py` (focus border, title)

## Implementation steps
1. Pure function `layout_signature(tab)`; recursive widget builder with `styles.width/height = f"{ratio}fr"`.
2. Attach/detach diff on rebuild (set of visible live pane ids before/after).
3. Route ws `out/replay` to the matching view via `dict[pane_id, TerminalPaneView]` in the layout view.
4. Prefix router (pure) + tests; hook at App level with priority binding for the prefix key only.
5. Actions module; confirm dialog for close (Textual ModalScreen, Y/N).
6. Focus neighbour by geometry.

## Todo
- [ ] layout builder + signature
- [ ] attach/detach diff + output routing
- [ ] stopped placeholder
- [ ] prefix router + tests
- [ ] actions + close confirm
- [ ] Pilot test

## Success criteria (how checked)
- `pytest -q tests/test_tui_prefix_key_router.py`: `C-a` then `z` -> "zoom"; `C-a C-a` -> literal `\x01`; timeout disarms.
- `pytest -q tests/test_tui_split_layout_view_pilot.py` (real daemon): tab with 2 panes split row -> two `TerminalPaneView`s side by side
  (x of second > x of first); press keys `e c h o space h i enter` -> `pane.read` of focused pane contains `hi`;
  `C-a %` -> 3 panes; `C-a z` -> only one view mounted; ws shows `detach` of hidden panes (assert `ctx` attached listeners count).
- Manual: two claude agents side by side, switch focus, type in each, zoom.

## Risks
- Rebuild flicker on layout change -> rebuild only on signature change.
- Prefix collides with agent shortcuts (Ctrl+A = line start in shells) -> double-press passes it through; prefix configurable from settings.
- Many panes = many pyte screens: memory ~ cols*rows*history per pane; client keeps no history (pyte `Screen`, not `HistoryScreen`) in this slice.

## Security
Close/kill actions need confirm; same RPCs the web UI uses.

## Next steps
Phase 05 adapts this to narrow terminals.
