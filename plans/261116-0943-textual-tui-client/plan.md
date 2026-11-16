---
title: "Textual TUI client for Drover"
description: "Add `dr tui`: a Textual client in the user's own terminal (sidebar, split panes, live terminals, restore dialog); daemon and web UI unchanged."
status: implemented (manual + frozen-build checks not run)
priority: P2
effort: 14h
branch: main
tags: [tui, textual, client, terminal-emulation]
created: 2026-11-16
---

# Textual TUI client (`dr tui`)

## Goal
New client `src/drover/tui/` talking to the existing daemon over `/ws` (same protocol as web UI and `dr attach`).
Zero daemon / web UI changes. Minimum slice first, parity later.

## Key decision (details: phase 01)
Client-side emulation: own small widget = **pyte** (already a dependency) fed from ws `replay` + `out`,
drawn with Textual's Line API (`render_line` -> `Strip`). Not `textual-terminal` (spawns its own process),
not daemon `pane.screen` (plain text only via `pane.read`, throttled 0.15 s, colours need a daemon change).
Phase 01 is a **go/no-go gate**: measure before building the rest.

## Architecture
```
dr tui ──> TuiApp (Textual)
            ├─ DaemonConnection (aiohttp ws: rpc/res, ev state|status|pane, out/replay, in, attach)
            ├─ WorkspaceSidebar (spaces > tabs > panes + state glyph)
            ├─ SplitLayoutView (tab.layout tree -> nested Horizontal/Vertical)
            │    └─ TerminalPaneView xN (pyte screen + Line API, keys -> {"t":"in"})
            └─ RestoreStoppedDialog (session.resume / session.discard)
```

## Phases
| # | Phase | Effort | Status |
|---|-------|--------|--------|
| 01 | [Spike: terminal emulation in Textual (gate)](phase-01-spike-terminal-emulation-gate.md) | 3h | done |
| 02 | [Daemon connection + app shell + `dr tui`](phase-02-daemon-connection-and-app-shell.md) | 2h | done |
| 03 | [Sidebar with agent states](phase-03-workspace-sidebar-with-states.md) | 2h | done |
| 04 | [Split layout, focus, input, prefix keys](phase-04-split-layout-focus-and-prefix-keys.md) | 3h | done |
| 05 | [Responsive layout (narrow terminals)](phase-05-responsive-narrow-layout.md) | 1.5h | done |
| 06 | [Restore dialog for stopped panes](phase-06-restore-stopped-panes-dialog.md) | 1h | done |
| 07 | [Packaging, docs, final test pass](phase-07-packaging-docs-final-tests.md) | 1.5h | done |

Order is strict (each phase builds on the previous). No parallel work.

## Dependencies
- New: `textual` (pin exact range after phase 01), dev: none (Pilot ships with Textual).
- Reuse: `daemon_client.ensure_daemon`, `core/terminal_key_names.KEYS`, `core/terminal_mode_tracker`,
  `core/split_layout_tree.pane_ids`, `tests/daemon_harness.py`.

## Test strategy
- Pure logic (emulator wrapper, key mapping, layout mapping, state helpers): plain pytest.
- Widgets/app: Textual Pilot `app.run_test(size=...)` headless, fed by a real daemon via `daemon_harness`.
- Low RAM: one spec file per run, `--runInBand` style (`pytest -q tests/<file>`), capped with systemd-run.

## Out of scope (later parity work)
Chat view, files/changes/worktrees, command palette, search, mouse, scrollback/copy mode, remote machines UI,
settings, notifications (daemon already sends desktop ones), detach-and-keep-TUI-server (Herdr-style).

## Unresolved questions
See end of [phase-07](phase-07-packaging-docs-final-tests.md#unresolved-questions).
