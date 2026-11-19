# dr wait --children all/any

## Context
- Plan: [plan.md](plan.md)

## Overview
- Priority: P1
- Status: done
- New RPC `pane.wait_children {caller, mode: all|any, timeout}`; `dr wait --children all|any`.

## Key insights
- all: resolves when no child is working (done/idle/blocked/exited); no children → reason `no_children`.
- any: resolves on the next child transition into done/blocked/exited (or working→idle); none working → `none_working`.
- Result: {reason, pane?, state?, children: [{pane, name, state}]}; timeout = error code 2 like pane.wait.
- Registers the wait so phase 4 does not type notes that the wait already delivers.

## Related code files
- src/drover/rpc/methods_panes.py
- rust/crates/drover-daemon/src/methods/panes.rs
- src/drover/cli/cli_main.py, cli_commands_agents.py
- tests/test_daemon_orchestration_children.py

## Implementation steps
1. Python: subscribe hub 'status' for children, asyncio.Future.
2. Rust: same with hub.subscribe + oneshot.
3. CLI: target optional when --children is given.
4. Tests: all / any / no_children / timeout.

## Todo
- [x] Python: subscribe hub 'status' for children, asyncio.Future.
- [x] Rust: same with hub.subscribe + oneshot.
- [x] CLI: target optional when --children is given.
- [x] Tests: all / any / no_children / timeout.

## Success criteria
- Same JSON from both daemons for the four cases.

## Risks / security
- Agents typing into other agents: keep the existing permission gate (`gate_agent_input`); notes never answer a permission prompt.
