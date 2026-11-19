# Phase 01: Rust fast path in drover-cli

## Context Links
- Python: `src/drover/cli/cli_main.py`, `cli_commands_agents.py`, `cli_commands_agent_input.py`,
  `src/drover/daemon/daemon_client.py`, `local_http.py`
- Rust: `rust/crates/drover-cli/src/{main.rs,hook_claude.rs}`, `drover-daemon/src/paths.rs`

## Overview
Priority P1. Status: in progress. Native handling of the hot commands; everything else delegates to Python.

## Key Insights
- Python argparse accepts abbreviations, options anywhere, `--x=v`. Fast parser accepts only exact flags
  (`--flag v` / `--flag=v`) and delegates on anything else, so help/usage errors keep Python's wording.
- `json.dumps` defaults: `", "`/`": "` separators, ASCII-only (`\uXXXX`, surrogate pairs); `indent=1` uses `","`.
- Python text stdout on Windows writes `\n` as `\r\n`.
- argparse `--timeout` default is the int `600` (type not applied to defaults); a given value is a float.
- `call()` adds `caller=$DR_PANE_ID`; RPC error -> `error: <msg>` exit `code>0 ? code : 1`; transport error -> exit 10.
- Delegating when the daemon is unreachable keeps autostart (Python `ensure_daemon`) in one place.

## Requirements
- Same stdout/stderr bytes and exit codes as Python for every native command.
- No heavy deps: serde_json (preserve_order) + std only.
- Ctrl+C while Python child runs: parent ignores it, child handles it, exit code passes through.

## Related Code Files
- Modify: `rust/crates/drover-cli/Cargo.toml`, `src/main.rs`, `src/hook_claude.rs`
- Create: `src/daemon_rpc.rs`, `src/python_json.rs`, `src/fast_args.rs`, `src/fast_commands.rs`,
  `src/python_fallback.rs`

## Implementation Steps
1. Feature `server` (optional drover-daemon); `server run` delegates when off.
2. `daemon_rpc`: state dir, daemon.json, HTTP/1.0 POST /rpc, Unreachable vs Rpc error vs Transport error.
3. `python_json`: dumps compact + indent=1, Python `str()` of values.
4. `fast_args`: strict parser -> `Option<FastCommand>`.
5. `fast_commands`: run + print exactly like Python.
6. `python_fallback`: run sibling `dr-py(.exe)`, ignore Ctrl+C in parent, exit with child's code.
7. Unit tests for json + parser.

## Todo List
- [ ] feature flag  - [ ] daemon_rpc  - [ ] python_json  - [ ] fast_args  - [ ] fast_commands
- [ ] python_fallback  - [ ] unit tests  - [ ] builds on windows-gnu

## Success Criteria
Unit tests pass; `dr ls` < 30 ms on Windows; parity tests (phase 03) green.

## Risk Assessment
- Output drift breaks agent scripts -> parity tests compare against Python on a live scratch daemon.
- Rare argv quoting differences (Rust vs CPython CRT parsing): both follow MSVC rules.

## Security Considerations
Token only read from daemon.json, sent to 127.0.0.1 only; never printed.

## Next Steps
Phase 02.
