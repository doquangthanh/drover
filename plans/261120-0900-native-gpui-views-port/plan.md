---
title: "Native GPUI views: Agents, Changes, Files, Inbox, Settings, Machines"
description: "Draw the views drover-native still opens in the browser inside the GPUI window. Files is view-only first."
status: in-progress
priority: P1
branch: main
tags: [rust, gpui, desktop, native, views]
created: 2026-11-20
---

# Native GPUI views

## Why
`drover-native` opens Agents, Files, Changes, Inbox, Settings and Machines in the browser
(`WEB_VIEWS` in `actions.rs:36`). The user does not want to use the web for these (2026-11-20).
Parent plan: [native GPUI desktop](../261119-1749-native-gpui-desktop/plan.md) (MVP said these stay web-only; this plan ports them).

## Decisions (user, 2026-11-20)
- Port all six views: Agents (tree), Changes, Files, Inbox, Settings, Machines.
- Files is **view-only** in the first version: tree + read file + diff + select/copy. Editing keeps "Open in browser".
- Plan first, then one view per phase, build + check after each.
- Until a view is ported its button opens the web UI (user chose A, then B: port them all), 2026-11-20.
- Herdr-style (user, 2026-11-20): Agents / Files / Changes are a right panel beside the terminals that follows the
  focused pane (`views/panel.rs`); Inbox / Machines / Settings stay full views. Daemon `files.*` take `pane`.
- GPUI is the default window from now on (user, 2026-11-20): `drover` / `drover app` start the daemon, then
  `drover-native` next to them; the Tauri window stays as fallback (`DROVER_WINDOW=webview`, or no/unstartable
  drover-native). Code: `rust/crates/drover-desktop/src/window_choice.rs`.

## Shape
```
DroverApp.view: Terminals | Agents | Changes | Files | Inbox | Settings | Machines
   topbar buttons / sidebar links  ──► set view (no browser)
   main area: view == Terminals ? tab_body : views::<view>::render
   data: Store (ws events) + rpc_then(...) replies, same RPCs as the web UI
   fallback: "Open in browser" item kept per view (web stays for phone / other machines)
```
No daemon change: every RPC already exists (web UI uses them).

## Phases
| # | Phase | Status |
|---|---|---|
| 0 | [View switching + shared widgets (list, split, text input, scroll) + Store extras](phase-00-view-switching-and-shared-widgets.md) | done (RpcCell + scroll list moved to phase 1) |
| 1 | [Agents tree: list, inspector, Messages, Policy, Flow lanes, send/stop](phase-01-agents-tree-view.md) | done (no sub-agent lanes / activity bars yet) |
| 2 | [Changes: worktrees, changed files, coloured diff, push/PR, remove/prune](phase-02-changes-view.md) | done (not checked by eye yet) |
| 3 | [Files (view-only): tree, read file, git status, diff, select/copy](phase-03-files-view-readonly.md) | done: no syntax colours, Copy file instead of select (not checked by eye yet) |
| 4 | [Inbox: needs-you list, allow/deny policy prompts, mark read](phase-04-inbox-view.md) | done: no notification side panel / machine filter (not checked by eye yet) |
| 5 | [Settings + Machines: forms, toggles, settings.write, machine add/test/remove](phase-05-settings-and-machines-views.md) | done: files read-only + Open in editor; no Appearance / rules tester (not checked by eye yet) |
| 6 | [Wrap-up: drop browser fallback for ported views, docs, changelog, parent plan](phase-06-wrap-up-docs-release.md) | todo |

Order = value / effort: Agents and Changes are used daily; Settings/Machines need the most form widgets.

## Checks (every phase)
- `cargo build --release -j2 -p drover-desktop-native` inside the RAM cap (3G, `CPUQuota=200%`).
- `cargo test -p drover-desktop-native` for pure logic ported from TS (tree rows, diff parse...), one run per phase.
- Run the app against the live daemon, screenshot the view, compare with the web view.
- `cargo clippy -p drover-desktop-native` once per phase.

## Constraints
- Files < 200 lines: new code under `src/views/` (one module per view, split by part).
- GPUI 0.2.2 has no ready text input / list widgets: phase 0 builds the minimum ones.
- Low RAM: one heavy job at a time, never parallel builds.

## Risks
- Text input (IME, Vietnamese Telex) for Agents send / Settings / Machines: reuse `terminal_input.rs` IME code.
- Syntax colours in Files: new dependency (syntect) costs build time/RAM. Phase 3 decides; plain text is the fallback.
- Big diffs / files: render only visible rows (`uniform_list`).
