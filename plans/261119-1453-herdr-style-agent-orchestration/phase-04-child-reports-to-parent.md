# Children report to their parent

## Context
- Plan: [plan.md](plan.md)

## Overview
- Priority: P1
- Status: done
- Daemon types `<dr from="%7 review" state="done">read it: dr read review</dr>` into the parent agent; `dr send parent` reaches the parent.

## Key insights
- Hook point: where messages.add_state(child, parent, done|blocked|exited) fires (status monitor + exit hook).
- Queue per parent; flush on the monitor tick when safe: parent alive, kind != shell, not blocked, no active wait covering the child, no unfinished draft.
- Draft: UI keystrokes into a pane (ws 'in' / pane.write) set draft=true + last_key_at; a CR clears it. Draft blocks notes while last key < 60 s ago.
- Setting `orchestration.notes` (default true).
- `dr send parent ...`: target `parent` resolves to the caller's parent; text wrapped in `<dr from=...>` when the caller is a child of the target.

## Related code files
- src/drover/core/session_manager.py
- src/drover/core/status_monitor.py
- src/drover/core/pane_session.py
- src/drover/daemon/ws_client_session.py
- src/drover/rpc/methods_panes.py
- src/drover/rpc/target_resolver.py
- src/drover/rpc/methods_agent_input.py
- rust/crates/drover-daemon/src/{manager_panes.rs,status_monitor.rs,ws_session.rs,methods/panes.rs,methods/agent_input.rs,rpc.rs}
- tests/test_daemon_orchestration_children.py

## Implementation steps
1. Add parent_notes queue + draft fields.
2. Enqueue at add_state call sites.
3. Flush in monitor tick via the submit routine.
4. Wait registration drops queued notes for covered children.
5. `parent` target + from-tag.
6. Tests with a fake agent parent.

## Todo
- [x] Add parent_notes queue + draft fields.
- [x] Enqueue at add_state call sites.
- [x] Flush in monitor tick via the submit routine.
- [x] Wait registration drops queued notes for covered children.
- [x] `parent` target + from-tag.
- [x] Tests with a fake agent parent.

## Success criteria
- Note arrives in a fake agent parent; nothing typed into a shell parent, a blocked parent or during a draft.

## Risks / security
- Agents typing into other agents: keep the existing permission gate (`gate_agent_input`); notes never answer a permission prompt.
