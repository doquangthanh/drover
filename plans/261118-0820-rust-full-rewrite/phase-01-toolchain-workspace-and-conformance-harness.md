# Phase 01: Toolchain, workspace, conformance harness

## Context Links
- [plan.md](plan.md), `tests/daemon_harness.py`, `docs/system-architecture.md`

## Overview
- Priority: P1. Status: done. Effort: 6h.
- Install Rust, create the Cargo workspace, let the Python test suite talk to an external daemon binary.

## Key Insights
- Tests boot the daemon in-process (`build_context` + `build_app`). Most of them only use `/rpc` and `/ws`,
  so they can run against any binary that speaks the same protocol.
- No Rust toolchain on the machine today.

## Requirements
- rustup in `~/.cargo` (no sudo), stable toolchain, `rustfmt`, `clippy`; Windows target added in phase 09.
- `rust/` workspace with empty crates that build.
- `DROVER_TEST_DAEMON_BIN=<path>` makes the harness start `<path> server run --port <free> --state-dir <tmp>`,
  read `daemon.json`, and use real HTTP/WS clients instead of aiohttp TestClient.
- A cap wrapper `scripts/cargo-capped.sh` (systemd-run MemoryMax=3G, MemorySwapMax=0, CPUQuota=200%, nice, `-j2`).

## Architecture
```
pytest ── harness ──┬─ default: in-process Python app (today)
                    └─ DROVER_TEST_DAEMON_BIN: spawn binary ── HTTP/WS ── same assertions
```

## Related Code Files
- Create: `rust/Cargo.toml`, `rust/crates/*/Cargo.toml` + `src/lib.rs|main.rs`, `scripts/cargo-capped.sh`,
  `rust/rust-toolchain.toml`.
- Modify: `tests/daemon_harness.py` (external mode), `.gitignore` (`rust/target`).

## Implementation Steps
1. Install rustup (`--profile minimal`, add rustfmt, clippy).
2. Create workspace and crates; `[profile.release]` with `lto = "thin"`, `opt-level = "s"`, `strip = true`, `panic = "abort"`.
3. Write `scripts/cargo-capped.sh`; set `CARGO_BUILD_JOBS=2` in `rust/.cargo/config.toml`.
4. Add external mode to the harness; mark tests that read in-process internals with `@pytest.mark.inprocess` and skip them in external mode.
5. Prove it: run one RPC test file against the Python daemon started as a subprocess (`dr server run`).

## Todo List
- [x] rustup installed, `cargo --version` works (1.100.0)
- [x] workspace builds (capped)
- [x] harness external mode (`tests/external_daemon_harness.py`; tests touching `daemon.ctx` auto-skip)
- [x] one test file green against Python daemon subprocess (layout: 5 passed, 5 skipped)

## Success Criteria
- `scripts/cargo-capped.sh build` passes; `DROVER_TEST_DAEMON_BIN=$(which dr) pytest tests/test_daemon_rpc_layout.py` green.

## Risk Assessment
- Some tests poke internals: tag them, list them, port their intent to Rust unit tests later.

## Security Considerations
- External mode still uses a random token per run; never listen beyond 127.0.0.1 in tests.

## Next Steps
- Phase 02.
