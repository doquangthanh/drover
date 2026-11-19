---
title: "Windows: Rust daemon by default"
description: "drover.exe's `server run` hands over to the Rust daemon inside runtime dr.exe; Python daemon stays as fallback."
status: in-progress
priority: P1
branch: main
tags: [rust, daemon, windows, perf]
created: 2026-11-19
---

# Windows: Rust daemon by default

## Goal
Windows daemon start ~1.4 s / ~91 MB idle (Python) -> Rust (Linux measured 7.6 MB RSS). Decision (user, 2026-11-19):
default on once the conformance suite passes on Windows; Python fallback when the Rust daemon is missing or
`DROVER_ENGINE=python`. Toolchain: GNU + WinLibs MinGW locally ("fastest"), MSVC + crt-static in CI.
Follows rust-full-rewrite phase 09 (Windows part).

## Design
```
drover.exe (Python: window + CLI) ── server run ──> runtime/<ver>/dr.exe server run   (Rust daemon, feature server)
                                       └─ no runtime yet / DROVER_ENGINE=python ──> Python daemon (installs runtime)
```
- One Rust binary: `dr.exe` built with the default `server` feature = fast CLI + daemon (same as Linux drover-server).
- First start of a new version runs the Python daemon (runtime not installed yet); it installs the runtime, the next
  start is Rust. Panes keep working either way (same session.json, daemon.json, protocol).
- Pane PATH from the Rust daemon: its exe dir (runtime) first; `shims/` added for the old `hd` name.

## Phases
| # | Phase | Status |
|---|-------|--------|
| 01 | Build Rust daemon on Windows (GNU + MinGW), run conformance suite (`DROVER_TEST_DAEMON_BIN`), fix gaps | in progress |
| 02 | Python `server run` -> runtime dr.exe on win32; CI builds dr.exe with `server`; shims on Rust pane PATH | todo |
| 03 | Windows-only checks: ConPTY panes, Ctrl+C, resize, claude hooks, notifications, self-update path | todo |
| 04 | Benchmark vs herdr, docs, changelog | todo |

## Risks
- Rust daemon never ran on Windows: the conformance suite is the gate; unknown failures may need fixes in drover-daemon.
- Self-update apply in Rust is Linux-only: on Windows the update must still swap drover.exe (check in phase 03).
- ring / windows-sys need a C toolchain: MinGW locally, MSVC in CI (differences possible).
