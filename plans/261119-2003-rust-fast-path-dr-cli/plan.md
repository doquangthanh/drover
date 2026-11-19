---
title: "Rust fast path for the dr CLI"
description: "Native dr.exe answers the hot agent commands over /rpc in ~20 ms and hands every other call to the Python dr unchanged."
status: in-progress
priority: P1
branch: main
tags: [rust, cli, perf, windows]
created: 2026-11-19
---

# Rust fast path for the dr CLI

## Goal
`dr` as fast as herdr (~22 ms per call). Measured 2026-11-19 on Windows, v0.1.38: `dr ls` 183 ms (runtime
dr.exe) / 195 ms (via `dr.cmd`), herdr `pane list` 24 ms. Python floor alone (`python -c pass`) is ~80 ms, so
the hot path must be native. Decision (user, 2026-11-19): partial revival of rust-full-rewrite phase 06 as a
fast path, not a full port.

## Design
```
dr.exe (Rust, runtime/<ver>/) ─ strict parse ─ hot command? ─ yes ─ POST /rpc (daemon.json) ─ print, exit code
                                                   └─ no / unsure / daemon unreachable ─ run dr-py.exe (Python) with same argv
```
- Native: `ls`, `send`, `read`, `wait`, `prompt`, `keys`, `wait-output`, `rename`, `kill`, `hook claude`.
- Anything else, `-h`/`--help`, unknown or abbreviated flags, bad values, no daemon -> Python, byte-for-byte as today.
- Output identical to Python: `json.dumps` style (ensure_ascii, separators, indent=1), `\r\n` on Windows,
  same error text and exit codes (RPC error code, 10 = daemon unavailable).
- Daemon feature: `drover-daemon` becomes optional feature `server` (default on, Linux bundle unchanged). The
  Windows build uses `--no-default-features`: small, pure Rust, builds with the GNU or MSVC toolchain.

## Phases
| # | Phase | Status |
|---|-------|--------|
| 01 | [Rust fast path in drover-cli](phase-01-rust-fast-path-in-drover-cli.md) | done (13 unit tests) |
| 02 | [Windows packaging: dr-py.exe + direct PATH](phase-02-windows-packaging-and-pane-path.md) | done locally; release CI (MSVC, crt-static) not run yet |
| 03 | [Parity tests, benchmark, docs](phase-03-parity-tests-benchmark-docs.md) | done: [benchmark](reports/benchmark-261119-2033-rust-fast-path-dr-vs-herdr.md) |

Review fixes (2026-11-19): delegate only when nothing was sent (after send: exit 10, no re-run); static CRT;
`--timeout` cap; Python `int()` error codes; Ctrl+C -> 130; broken pipe -> 1. A zip without `dr-py.exe`
falls back to the drover.exe in `.complete`, so `_check_zip` still only requires `dr.exe`.

## Out of scope
- Linux bundle switch to the Rust front door (same code; follow-up once Windows is proven).
- 2026-11-19 follow-up: `run` ported (pane creation 130 ms, herdr 136 ms); templates and attach stay Python.
- Porting `attach`, `status`, `server`, `tui` and the rest (stay Python).
