# Phase 03: Daemon server and RPC methods

## Context Links
- `src/drover/daemon/*`, `src/drover/rpc/*` (77 methods), `src/drover/core/{session_manager,state_store,event_hub,
  session_persistence,git_watcher,space_files,folder_browser,orchestration_policy}.py`, `src/drover/git/*`,
  `src/drover/config/settings_loader.py`

## Overview
- Priority: P1. Status: in progress (all groups ported except chat/notify/update/skill; daily-drive not done). Effort: 30h.
- Rust `dr server run` that the current React UI and Python CLI can use unchanged.

## Key Insights
- WS messages: `rpc/res`, `in`, `attach/detach`, `ev` (state, pane, status, policy, machines, resync), `out`, `replay`.
- Error codes are CLI exit codes (1 general, 2 timeout, 3 not found, 4 policy, 5 bad params, 6 blocked, 7 stalled, -32601).
- `session.json`, `daemon.json`, `chats/` live in `~/.local/state/drover`: same format so either daemon can take over.

## Requirements
- tokio + axum: `/`, `/ui/`, `/ui/assets/` (immutable), `/static/`, `/health`, `/rpc` (POST JSON), `/ws`; token check
  on every data channel; 503 "UI not built" when web_dist missing; same listen-address rules.
- web_dist embedded in the binary (`rust-embed`) with an override dir for dev.
- RPC groups in order: system/state, workspace, panes, layout, agent input (`pane.prompt`, `pane.wait`, `pane.wait_output`,
  `pane.keys`), files/fs/search, git/worktree, settings/keys/rules/fonts, subagents/messages.
- Settings: same TOML files and defaults.

## Architecture
```
axum router ─ /rpc ─┐
             /ws ───┼─> RpcRegistry (name -> async fn(ctx, Value) -> Result<Value, RpcError>)
                    └─> WsSession (out queue, attach set, coalesced "out" per pane)
Ctx { SessionManager, EventHub (broadcast), StateStore, Settings, GitWatcher }
```

## Related Code Files
- Create: `rust/crates/drover-proto/src/{ws.rs, rpc_error.rs, state.rs}`, `rust/crates/drover-daemon/src/{main_loop.rs,
  http_routes.rs, ws_session.rs, rpc_registry.rs, methods/*.rs (one file per Python methods_*.py), state_store.rs,
  session_persistence.rs, event_hub.rs, git_watcher.rs, settings.rs}`

## Implementation Steps
1. Router, token, static serving, `/health`, `daemon.json` write/remove; `test_web_ui_static_serving.py` green.
2. State + event hub + WS session; frontend loads and shows spaces.
3. Port method groups one at a time; after each, run the matching Python test file against the binary
   (`DROVER_TEST_DAEMON_BIN`), one file per run, capped.
4. Session persistence: Python-written `session.json` resumes in Rust and back (round-trip test).
5. Daily-drive: use the Rust daemon with the current window for a day; log gaps.

## Todo List
- [x] http + ws + token (axum; constant-time token; traversal-safe static)
- [x] state/event hub (state built at send time, so no listener ever re-locks the manager)
- [x] system, workspace, panes, layout, agent input, files/fs, git/worktree, subagents ported: 61 conformance tests pass, 15 skip (in-process only); `dr hook claude` in the Rust CLI
- [ ] notify.test, update.*, skill.text (phases 05/06); chat.* (phase 04)
- [x] session.json in the Python format (written by Rust, read back; Python->Rust load not yet tested by hand)
- [x] PSS measured (release): 5.1 MB idle, 5.9 MB with 5 shell panes (Python: ~106 MB idle)
- [ ] daily-drive the Rust daemon with the real web UI / window

## Success Criteria
- All `test_daemon_rpc_*` files (except tagged in-process ones) green against Rust; UI works with no frontend change;
  daemon idle <= 15 MB.

## Risk Assessment
- Hidden behaviour in Python (timings like `pane.wait` stall detection): copy constants, port tests first.

## Security Considerations
- Constant-time token compare; refuse 0.0.0.0; path traversal checks on files.* and static routes.

## Next Steps
- Phase 04 (chat.* methods), phase 06 (CLI).
