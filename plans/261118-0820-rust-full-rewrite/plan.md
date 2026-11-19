---
title: "Rewrite Drover in Rust"
description: "Replace the Python daemon, CLI, chat, remote, desktop window (PyQt/QtWebEngine) and TUI with Rust; keep the React frontend and the /ws + /rpc protocol unchanged."
status: planned
priority: P1
effort: ~150h
branch: feature/rust-rewrite
tags: [rust, rewrite, memory, daemon, tauri, tui]
created: 2026-11-18
---

# Rewrite Drover in Rust

## Goal
Cut RAM and startup time to Herdr's level. Measured today: Python daemon ~106 MB PSS, each PyQt window ~300 MB
+ 3-4 QtWebEngine processes. Targets: daemon <= 15 MB idle, `dr` CLI < 10 ms, desktop window < 120 MB total.

## Decisions (agreed 2026-11-18)
- Everything in phases; Drover stays usable at every step (Python and Rust daemons are interchangeable).
- Chat drives the `claude` CLI directly (`--output-format stream-json`, stdio control protocol). No Python.
- Linux + Windows, same as today.
- rustup installed user-local; every cargo build runs capped (MemoryMax=3G, `-j2`).

## Key rule: the protocol is the contract
React frontend, `dr attach`, scripts and agents only see `/ws`, `/rpc`, `/health`, `daemon.json`, `session.json`,
`chats/` and CLI exit codes. The Rust daemon keeps these byte-compatible, so:
- the frontend is not touched (except the desktop shell in phase 07);
- existing Python tests become a **conformance suite**: `tests/daemon_harness.py` gets a mode that runs them against
  an external daemon binary (`DROVER_TEST_DAEMON_BIN`).

## Architecture
```
drover (Tauri v2, system webview) ─┐
browser / phone ───────────────────┼─ /ws /rpc (token) ──> dr server  (Rust, tokio + axum)
dr tui (ratatui) ──────────────────┤                         ├─ panes: portable-pty + alacritty_terminal
dr <cmd> (clap CLI) ── /rpc ───────┘                         ├─ chat: claude CLI stream-json
                                                             ├─ remote: russh links to other machines
                                                             └─ state: session.json, chats/, daemon.json
```
Cargo workspace `rust/`: `drover-proto` (wire types), `drover-core`, `drover-daemon`, `drover-cli` (bin `dr`,
includes `server run` and `tui`), `drover-tui`, `drover-desktop` (bin `drover`).

## Phases
| # | Phase | Effort | Status |
|---|-------|--------|--------|
| 01 | [Toolchain, workspace, conformance harness](phase-01-toolchain-workspace-and-conformance-harness.md) | 6h | done |
| 02 | [Pane core: PTY, terminal emulation, status detection (gate)](phase-02-pane-core-pty-emulation-and-status.md) | 24h | done (gate: GO) |
| 03 | [Daemon server and RPC methods](phase-03-daemon-server-and-rpc-methods.md) | 30h | in progress |
| 04 | [Chat over the claude CLI](phase-04-chat-over-claude-cli.md) | 14h | done (UI click-through pending) |
| 05 | [Remote, notify, policy, self-update](phase-05-remote-notify-policy-and-self-update.md) | 18h | done (update swap -> 09; real-host ssh not run) |
| 06 | [CLI `dr`](phase-06-cli-dr.md) | 12h | partly revived 2026-11-19 as a fast path (hot commands in Rust, rest Python): [plan](../261119-2003-rust-fast-path-dr-cli/plan.md) |
| 07 | [Desktop window on Tauri](phase-07-desktop-window-on-tauri.md) | 14h | in progress |
| 08 | [TUI on ratatui](phase-08-tui-on-ratatui.md) | 18h | dropped (hybrid: Python TUI stays) |
| 09 | [Packaging, cutover (hybrid)](phase-09-packaging-cutover-and-python-removal.md) | 14h | Linux done locally; CI + Windows pending |

Phase 02 is a go/no-go gate (terminal emulation fidelity + RAM). 03-06 can ship as a Rust daemon used by the
current Python window before 07-08 exist.

## Dependencies / risks (details in phase files)
- `alacritty_terminal` API is not semver-stable: pin the version.
- Tauri on Linux needs system WebKitGTK (no longer self-contained like the Qt bundle); xterm.js WebGL on WebKitGTK must be measured.
- The claude CLI control protocol (permission prompts) is not formally documented: mirror what claude_agent_sdk sends.
- Low-RAM machine: one cargo build at a time, capped; no parallel agents.
