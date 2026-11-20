# Phase 00: View switching + shared widgets

## Context Links
- `rust/crates/drover-desktop-native/src/{workspace_app,topbar,sidebar,actions,widgets}.rs`
- `rust/crates/drover-proto/src/{store,wire}.rs`
- Web: `frontend/src/views/view-registry.ts`, `frontend/src/main.tsx` (`OPENABLE`)

## Overview
Priority P1 · Status done (2026-11-20) · Base for every later phase.

## Key Insights
- Topbar buttons call `open_web("tree"|"files"|"changes")`; status bar branch chip calls `open_web("changes")`;
  sidebar Inbox/Machines/Settings also go to the browser.
- `Store` keeps only spaces/tabs/panes. Views also need `orchestration`, `policy_pending`, `machines`
  from the `state` snapshot, and the `messages` event (sub-agent start/stop) as a refetch tick.
- `rpc_then` already gives request/reply; views need a small "loading / error / data" holder on top.

## Requirements
- `enum View { Terminals, Agents, Changes, Files, Inbox, Settings, Machines }` in `DroverApp`, default Terminals.
- Topbar/sidebar/status-bar buttons switch the view; selected button highlighted; Esc or clicking a tab returns to Terminals.
- Each view has a "Open in browser" small action (keeps `open_web`).
- Store extras: `orchestration: Value`, `policy_pending: Vec<..>`, `machines: Value`, `messages_tick: u64`.
- Widgets: scrollable list with selected row, two-column split with fixed left width, one-line text input
  (typing, IME, backspace, enter, paste), button, toggle, tabs strip, empty/loading/error states.
- Non-functional: switching view < 50 ms; no extra RAM while a view is closed.

## Architecture
```
workspace_app.rs  view: View ── render(): match view
views/mod.rs      View enum, dispatch, RpcCell<T> {loading, error, data}
views/widgets/    list.rs, split.rs, text_input.rs, controls.rs (button, toggle, tabs)
drover-proto      store.rs: extras from state snapshot + "messages" event
```

## Related Code Files
- Modify: `workspace_app.rs`, `topbar.rs`, `sidebar.rs`, `actions.rs`, `main.rs` (mod), `drover-proto/src/store.rs`, `wire.rs`
- Create: `src/views/mod.rs`, `src/views/rpc_cell.rs`, `src/views/widgets/{mod,list,split,text_input,controls}.rs`
- Delete: none

## Implementation Steps
1. Add `View` + `view` field; render switch in `DroverApp::render`.
2. Rewire topbar (Agents/Files/Changes), status-bar branch chip, sidebar Inbox/Machines/Settings to `set_view`.
3. Store extras + `messages` event; unit tests in `drover-proto/src/tests.rs`.
4. `RpcCell<T>` + helper `fetch(method, params, into)` on top of `rpc_then`.
5. Widgets; text input reuses IME handling from `terminal_input.rs` (`EntityInputHandler`).
6. Placeholder body per view ("coming in phase N" + Open in browser) so every button works now.

## Todo List
- [x] View enum + switching (`views/mod.rs`)
- [x] Buttons rewired, browser fallback kept as action
- [x] Store extras + tests (`drover-proto` 6/6)
- [ ] RpcCell + fetch helper: moved to phase 01 (`rpc_reply` with errors is done)
- [x] Widgets: split, row, button, tab, toggle, note (`views/ui.rs`), text input (`views/text_input.rs`); scroll list moved to phase 01
- [x] Build (capped), test, screenshot
- [x] Review fixes: IME commit never deletes text after the cursor, keys queued until the IME commits,
      terminals take focus back when shown or when a confirm opens
- [ ] Vietnamese Telex typed by hand (user)

## Success Criteria
- Clicking Agents/Files/Changes/Inbox/Settings/Machines never opens the browser; shows the native placeholder.
- Text input accepts Vietnamese Telex in a test field (manual check by the user).
- `cargo test -p drover-proto` passes.

## Risk Assessment
- Text input in GPUI 0.2.2 is hand-written (Zed's editor is not a public crate): keep it one-line, minimal.
- Focus: keys must go to the input, not the terminal, while a view is shown.

## Security Considerations
- Same token/port from `daemon.json` as today; no new network surface.

## Next Steps
Phase 01 (Agents tree).
