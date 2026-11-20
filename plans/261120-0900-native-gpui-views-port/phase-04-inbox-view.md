# Phase 04: Inbox view

## Context Links
- Web: `frontend/src/views/inbox-view.tsx`

## Overview
Priority P2 · Status todo · ~110 lines to port.

## Key Insights
- Data from Store: panes with `state == "blocked"` or `unread`; `policy_pending` from state (phase 00 extras).
- Actions: `policy.decide {id, allow, machine?}`; opening the inbox marks unread panes read via `pane.focus`.

## Requirements
- Two groups: "Agents asking to act" (policy prompts: source → target, text, Allow / Deny) and
  "Needs you / finished" panes (click → Terminals + focus pane).
- Sidebar Inbox count stays in sync.

## Architecture
```
views/inbox.rs   one file (< 200 lines): groups, rows, actions
```

## Related Code Files
- Modify: `views/mod.rs`, `sidebar.rs`
- Create: `views/inbox.rs`

## Implementation Steps
1. Rows from Store + extras.
2. Allow/Deny RPC, mark-read on open.
3. Build, screenshot vs web `#inbox`.

## Todo List
- [ ] rows
- [ ] actions
- [ ] Build, screenshot

## Success Criteria
- Same items as web inbox; Allow/Deny clears the prompt.

## Risk Assessment
- Mark-read on open changes state for other viewers too (same as web): keep identical behaviour.

## Security Considerations
- Allow grants an agent action: button text must show what is allowed.

## Next Steps
Phase 05.
