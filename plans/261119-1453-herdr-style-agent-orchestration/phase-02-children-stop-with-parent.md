# Children stop with their parent

## Context
- Plan: [plan.md](plan.md)

## Overview
- Priority: P2
- Status: done
- Default `kill_children_on_parent_exit = true`; `--outlive-parent` keeps one child running.

## Key insights
- Exit hook already kills children when the setting is on (both daemons).
- New pane meta flag `outlive_parent` (pane.create param) skips that child.

## Related code files
- src/drover/config/settings_loader.py
- src/drover/core/session_manager.py
- src/drover/core/pane_session.py
- src/drover/rpc/methods_panes.py
- rust/crates/drover-daemon/src/default_settings.toml
- rust/crates/drover-daemon/src/manager_panes.rs
- rust/crates/drover-daemon/src/methods/panes.rs
- rust/crates/drover-core/src/pane_session.rs (PaneMeta)
- src/drover/cli/cli_main.py, cli_commands_agents.py
- tests/test_daemon_orchestration_children.py (new)

## Implementation steps
1. Flip default in both settings files.
2. Add `outlive_parent` to PaneMeta + NewPane/create params (both).
3. Exit hook: skip children with the flag.
4. `dr run --outlive-parent`.
5. Test: parent exits → child exited; flagged child alive.

## Todo
- [x] Flip default in both settings files.
- [x] Add `outlive_parent` to PaneMeta + NewPane/create params (both).
- [x] Exit hook: skip children with the flag.
- [x] `dr run --outlive-parent`.
- [x] Test: parent exits → child exited; flagged child alive.

## Success criteria
- Conformance test passes on Python and Rust daemons.

## Risks / security
- Agents typing into other agents: keep the existing permission gate (`gate_agent_input`); notes never answer a permission prompt.
