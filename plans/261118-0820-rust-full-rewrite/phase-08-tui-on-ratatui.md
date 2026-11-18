# Phase 08: TUI on ratatui

## Context Links
- `src/drover/tui/*` (Textual), `plans/261116-0943-textual-tui-client/`, `tests/test_tui_*.py`

## Overview
- Priority: P2. Status: todo. Effort: 18h.
- `dr tui` rebuilt with ratatui + crossterm; same features and keys as the Textual client.

## Key Insights
- The Textual TUI is a plain `/ws` client: sidebar, split layout, pane views (pyte), prefix keys (Ctrl+A),
  restore dialog, responsive modes (wide >= 100 cols, medium 60-99, narrow).
- Reuse `drover-core` screen code (alacritty_terminal) for client-side emulation; render cells into ratatui buffers.

## Requirements
- WS client (tokio-tungstenite) with rpc futures, reconnect + re-attach.
- Sidebar tree with state glyphs, tab bar, split layout from `tab.layout`, pane view with colours/cursor.
- Prefix key router, goto picker, text input / confirm / restore dialogs.
- Attach visible panes only; coalesce structure events to one redraw per 100 ms.
- Ctrl+Q goes to the pane; quit is prefix `d`.

## Architecture
```
dr tui ─ App (ratatui) ─┬─ WsConnection
                        ├─ Sidebar / TabBar
                        ├─ SplitLayout ─ PaneView xN (alacritty Term -> cells)
                        └─ PrefixKeyRouter + dialogs
```

## Related Code Files
- Create: `rust/crates/drover-tui/src/{app.rs, ws_connection.rs, sidebar.rs, tab_bar.rs, split_layout.rs, pane_view.rs,
  key_to_bytes.rs, prefix_keys.rs, dialogs/*.rs, responsive_mode.rs, restore_logic.rs}`

## Implementation Steps
1. Port pure logic first with tests from `test_tui_prefix_key_router.py`, `test_tui_textual_key_to_bytes.py`,
   `test_tui_state_helpers.py`, `test_tui_tab_bar.py`, `test_tui_sidebar_and_picker_rows.py`.
2. WS connection + app shell; then sidebar, layout, pane view, dialogs.
3. Manual check: run claude in 3 panes, resize the terminal through all three modes.

## Todo List
- [ ] pure logic + tests
- [ ] ws connection
- [ ] views + dialogs
- [ ] manual check + RSS measured

## Success Criteria
- Feature parity with the Textual client; `dr tui` RSS < 20 MB.

## Risk Assessment
- Key encoding edge cases (Alt, function keys, kitty protocol): port the key tests first.

## Security Considerations
- Same token handling as the CLI.

## Next Steps
- Phase 09.
