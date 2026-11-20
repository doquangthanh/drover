# Phase 01: Agents tree view

## Context Links
- Web: `frontend/src/views/{tree-view.tsx,agent-tree-list.tsx,agent-tree-inspector.tsx,agent-flow-board.tsx,agent-flow-logic.ts,views-logic.ts}`
- Tests to port: `views/agent-flow-logic.test.ts`, `views/views-logic.test.ts`

## Overview
Priority P1 · Status done (2026-11-20) · ~400 lines of TSX/TS to port.

## Key Insights
- Tree rows come from the Store (`parent` on each pane): no RPC for the list.
- Messages: `messages.list {pane: root}`, refetched on panes change and on the `messages` event tick.
- Policy panel reads `state.orchestration` (Store extras from phase 00).
- Actions: `pane.send {pane, text}`, `pane.close {pane, subtree: true}`.

## Requirements
- Left: filterable tree (indent by depth, kind icon, state mark, age). Default selection = first root with children.
- Right top: inspector of the selected agent (name, state, cwd, command, parent, children count) + send box + Stop.
- Right body tabs: Flow (lanes per agent, time-ordered messages), Messages (reverse list), Policy (4 tiles).
- Click an agent row "Go to pane" switches to Terminals and focuses that pane.
- Selection/tab/filter survive leaving the view.

## Architecture
```
views/agents/mod.rs        layout: split(list | inspector + tabs)
views/agents/tree_logic.rs treeRows, rootOf, subtreeIds, withSubLanes (port of TS, unit-tested)
views/agents/list.rs       left list + filter input
views/agents/inspector.rs  details, send box, stop
views/agents/flow.rs       Flow lanes + Messages + Policy
```

## Related Code Files
- Modify: `views/mod.rs`, `workspace_app.rs` (nav state)
- Create: files above
- Delete: none

## Implementation Steps
0. From phase 00: `RpcCell` + fetch helper, scrollable list (`overflow_y_scroll` + id); drop the "Typed:" debug line.
1. Port pure logic + tests (`cargo test`).
2. List + filter, selection state on `DroverApp`.
3. Inspector + send/stop (confirm dialog for Stop, reuse `dialogs.rs`).
4. Messages fetch via `RpcCell`, Messages + Policy tabs.
5. Flow lanes (simple: one column per agent, rows by time; no curves in v1).
6. Build, screenshot vs web `#tree`.

## Todo List
- [x] Logic port + tests (`drover-proto/src/agent_tree.rs`, 4 tests)
- [x] List + filter (`views/agents/list.rs`)
- [x] Inspector + send box / Open / Stop subtree with confirm (`views/agents/inspector.rs`)
- [x] Messages / Policy (`views/agents/activity.rs`)
- [x] Flow lanes (no sub-agent lanes, no activity bars, ages instead of hh:mm)
- [x] Build, test, screenshot

## Success Criteria
- Same agents, parents and states as web `#tree` for the live session.
- Send text reaches the agent; Stop closes the subtree after confirm.

## Risk Assessment
- Flow board in web is an SVG-ish board; v1 is simpler lanes. Note the difference to the user.

## Security Considerations
- Stop is destructive: always confirm.

## Next Steps
Phase 02 (Changes).
