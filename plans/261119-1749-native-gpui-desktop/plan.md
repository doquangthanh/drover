---
title: "Native desktop app in GPUI (Herdr-style), replacing the Tauri + React window"
description: "Rust + GPUI desktop client of the existing daemon: sidebar, tabs, splits, GPU-drawn terminals. The React web UI stays as the phone/browser client."
status: planned
priority: P1
branch: feature/rust-rewrite
tags: [rust, gpui, desktop, terminal, performance]
created: 2026-11-19
---

# Native desktop app in GPUI

## Why
Switching space in the Tauri window takes 5-12 s on first open (measured in the real window 2026-11-19; daemon,
Claude, CPU, RAM and replay size ruled out). Herdr draws with GPUI straight to the GPU, no web view. Zed proves the
stack: GPUI + `alacritty_terminal` for its terminal.

## Shape (agreed 2026-11-19)
```
drover-server (Rust daemon, unchanged: /ws /rpc /health, daemon.json)
   ├── drover-desktop-native  (NEW: GPUI app, desktop)      replaces drover (Tauri) on Linux, later Windows
   ├── web UI (React)          kept as is for phone/browser, no new features
   └── dr / dr tui             unchanged
```
- The protocol is the contract: the new app is one more client, like the TUI. No daemon change in the MVP.
- Terminal emulation on the client with `alacritty_terminal` (already a drover-core dependency), fed by
  `replay` + `out`; drawn as a GPUI element (glyph runs per row, cursor, selection).

## Phases
| # | Phase | Status |
|---|---|---|
| 0 | [Spike: GPUI builds and runs here, one live terminal](phase-00-gpui-spike-go-no-go.md) | done: GO |
| 1 | [Daemon client + state store (ws, rpc, reconnect)](phase-01-daemon-client-and-state.md) | done |
| 2 | [Terminal element: emulator, GPU text, input, resize, scroll, select/copy, links](phase-02-terminal-element.md) | in progress: input/IME/resize/scroll, select/copy/paste, links done; Vietnamese typing not verified by hand |
| 3 | [Shell: sidebar (spaces, agents, states), tab bar, splits, zoom, status bar](phase-03-shell-sidebar-tabs-splits.md) | in progress: look matches the web UI (theme, Geist, icons, terminal font/colours); buttons not wired yet |
| 4 | [Keys (VS Code map), command palette, jump-to, notifications, inbox](phase-04-keys-palette-inbox.md) | todo |
| 5 | [Packaging: Linux bundle swaps the Tauri window; docs; release](phase-05-packaging-release.md) | todo |

### Decision (user, 2026-11-20)
GPUI becomes the default desktop window on Windows and Linux, replacing Tauri + WebView2. The web UI stays for
phones/other machines and for the views GPUI doesn't draw yet. Switch the default only once the daily basics work:
select/copy, clickable links, main shortcuts (new tab/pane, switch, close, zoom), web views reachable from the app.
Measured 2026-11-20 (Windows): Tauri window 114 MB (6 + 108 WebView2), GPUI 43-67 MB, herdr-app (GPUI) 70 MB.

MVP = phases 0-5. Views not in the MVP (Changes/diff, Files + editor, Settings, Machines, Agent tree, Chat) open the
existing web UI in the browser from a menu until each is ported.

## Gate
Phase 0 decides go/no-go: GPUI must build on this machine inside the caps (MemoryMax=3G, `-j2`) and render a live
`claude` pane at >= 60 fps with switching between two panes < 50 ms. If not: fall back to egui (same plan, phase 2
draws the grid itself).

## Constraints
- Low RAM: every cargo build capped; one heavy job at a time; first GPUI build may take long.
- Linux (X11 + Wayland) first; Windows after the MVP (GPUI has a Windows backend).
- Keep the Tauri window shippable until phase 5 swaps it.

## Risks
- GPUI API is young (0.2.x): pin the exact version.
- GPU/driver issues on some Linux machines: GPUI needs Vulkan; check on this machine in phase 0.
- Feature parity is large (React UI ~4.3k lines TSX + logic): MVP scope above is deliberate.
