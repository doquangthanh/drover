---
title: "Windows = Linux: one codebase, same parts, same build, same update"
description: "Remove every Windows/Linux difference except OS API shims and config; CI gate keeps them equal."
status: in-progress
priority: P1
branch: main
tags: [windows, linux, parity, tauri, packaging, ci]
created: 2026-11-19
---

# Windows = Linux parity

## Goal
After this, a feature or fix lands once and ships the same on both. Allowed differences only:
1. OS API shims behind one shared function (PTY/ConPTY, process lookup, paths, notify, `CREATE_NO_WINDOW`).
2. Config values (state dir, PATH separator, file names with `.exe`).
Everything else (parts, bundle layout, window, CLI, daemon, update flow, tests) identical.

## Differences found (audit 2026-11-19; all closed, see Phases)
| Area | Linux | Windows | Phase |
|---|---|---|---|
| Window | `drover` Rust/Tauri | `drover.exe` Python/pywebview | 01 |
| Native GPUI preview | yes | no | 01 |
| Bundle | folder: `dr`, `drover-server`, `drover`, `drover-native` | onefile `drover.exe` + runtime zip | 02 |
| Self-update | Rust swaps bundle | Rust calls `drover.exe self-update` | 02 |
| CI build | `-p drover-cli -p drover-desktop -p drover-desktop-native` | `-p drover-cli` | 02 |
| Follow cwd | yes | off (`manager.rs:178`) | 03 |
| Claude resume of typed claude | yes | off (`status_monitor.rs:113`) | 03 |
| Title kind fallback | off | on (`status_monitor.rs:152`) | 03 |
| Python daemon | not shipped as fallback | fallback + first start | 02 |
| arm64 | yes | no | out of scope (note) |
| Agent detection | done 51b3239 (one path) | done | - |

## Target layout (both OS)
```
<install>/                    Linux ~/.local/share/drover   Windows %LOCALAPPDATA%\drover\app
  dr[.exe]                    Rust CLI + daemon (fast path, server feature)
  dr-py[.exe] / _internal     Python CLI for the commands not ported (templates, attach, tui)
  drover[.exe]                Tauri window
  drover-native[.exe]         GPUI preview (opt-in)
```
Windows download stays one click: `drover.exe` (the window) installs this folder itself on first run (decision 1).

## Phases
| # | Phase | Status |
|---|---|---|
| 01 | [Tauri + GPUI windows build and run on Windows](phase-01-tauri-window-on-windows.md) | done (0.1.44) |
| 02 | [Same bundle, CI and self-update on both](phase-02-same-bundle-ci-update.md) | done (0.1.43-0.1.45); cleanup left: remove Python daemon, runtime installer, `self_update_windows.rs` once no install runs 0.1.4x |
| 03 | [Turn on the Windows-off features](phase-03-feature-gaps.md) | done (0.1.44): agent detection, claude resume, follow cwd, Windows Terminal font; title guess removed |
| 04 | [Parity gate in CI + docs](phase-04-parity-gate-docs.md) | ci.yml + code-standards done; architecture/README update left |

## Constraints
- Low-RAM machine: cargo `-j2`, one heavy build at a time. Local Windows toolchain GNU + WinLibs (dlltool on PATH).
- Protocol, session.json, daemon.json unchanged: old and new clients keep working during the switch.
- Existing Windows users: update from 0.1.4x onefile must land on the new layout without manual steps.

## Decisions (user, 2026-11-19)
1. Download stays one `drover.exe`. It IS the Tauri window (no separate launcher): run from outside the app folder,
   it fetches `drover-windows-x64.zip` of its own version (SHA-256 checked), unpacks to `%LOCALAPPDATA%\drover\app`,
   copies itself there, repoints shortcut/autostart, starts from there. Inside the folder it is just the window.
2. Python daemon: dropped like Linux. The migration release still keeps it as fallback; the next one removes it.
3. Names as Linux: `drover.exe` = Tauri window, `dr.exe` = Rust CLI + daemon, `dr-py.exe` = Python CLI.

## Unresolved questions
1. arm64 Windows: needed now or later?
