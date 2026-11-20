---
title: "Herdr feature parity for the native Drover window"
status: draft (waiting for the owner to pick the order)
created: 2026-11-20
---

# Source (read, not guessed)
herdrdev/herdr-app 0.1.16 (GPUI client, `gpui-pre` 0.3.8, UI = JS mods on a vendored `gpui-kit`), herdrdev/herdr-core
(`hc` CLI + daemon), herdrdev/herdr (terminal UI, ratatui), herdrdev/herdr-nix (cachix push, not relevant).
Drover native uses `gpui = "=0.2.2"`: Herdr's `gpui-kit` was NOT checked against it.

# Gap table
Status of Drover: read from code (step 2 done 2026-11-20). "check" = a part still not read.

| # | Herdr feature (source) | Drover native | Size |
|---|---|---|---|
| 1 | In-app toasts, `notify({title, body, level, action})` (`mods/toast`) | done (toasts.rs) | - |
| 2 | Settings: Look (theme light/dark/system, font, size, weight, line height, cell width) | partial: theme done (Appearance); font, weight, line height, cell width not done | medium |
| 3 | Settings: Alerts (channels per event, quiet hours) as controls | done (settings_alerts.rs; no per-event sound pick) | - |
| 4 | Settings: Updates, Machines | done | - |
| 5 | Settings: Privacy (telemetry opt-in) | skipped: Drover has no telemetry to opt into | - |
| 6 | Themes: presets + `themes/<name>.json` + `colors` overrides | partial: 3 built-in themes; no theme files or colour overrides | medium |
| 7 | App zoom (`app.zoom_in/out/reset`) | partial: terminal text zoom Ctrl+= / - / 0; chrome does not scale (px sizes everywhere) | - |
| 8 | Peek: open a worker without a pane over the tab, "keep as tab" | not done: every Drover agent already has a pane in a tab | - |
| 9 | Kept terminals (`terminal.keep/park/pin`, `hc run --keep`, `restore_screen`) | missing as a per-terminal flag; whole-session restore exists | large (daemon) |
| 10 | Tab settle/unsettle (`tab.settle`) | done (in memory only: not kept across restarts) | - |
| 11 | Terminal: paste image, select all, search, adjust selection | done: paste image (local panes), select all (palette), search | - |
| 12 | Layouts + mods (JS) | missing, by design far off | very large |
| 13 | `keys.json` with per-layout/mod key tabs | partial: keys.toml = keys after the prefix; native shortcuts are fixed in keys.rs | medium |
| 14 | Welcome, What's new, Feedback frames | welcome done; What's new and Feedback not done | small |
| 15 | `hc` CLI: run, run --bg, ls, attach, read, wait, kill | done in `dr` (fast_args.rs: ls, send, read, wait, kill, run, --bg, --name, attach); `--keep`, 180 s check-in, draft_wait, notes_quiet not checked | check |
| 16 | Remote machines over SSH, `vps/t7` addresses | done: machines view; addresses are `machine:pane` instead of `machine/tN` | - |

# Not copying
- Layouts/mods in JavaScript (#12) and the vendored `gpui-kit`: a different architecture, months of work.
- Multi-line in-app file editor: Herdr has none either (Settings is controls, files open in the editor).

# Proposed order (small and safe first)
1. Settings → Alerts controls + Privacy (3, 5).
2. (done) Confirm every "check" row by reading the code; table above is updated.
3. Look: theme runtime colours, then presets + theme files, font/size/line height (2, 6).
4. App zoom, tab settle, peek (7, 10, 8).
5. Daemon work: kept terminals, `hc`-style run/wait (9, 15), each with its own plan.

# Rules for each step
One heavy command at a time, capped (resource-limits.md). `cargo check` before and tests after. No commit without asking.
