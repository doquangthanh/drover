---
title: "Migrate herd web UI to Vite + React + TypeScript"
description: "Incremental port of src/herd/web vanilla JS to a Vite/React/TS/Zustand app served by the daemon, with parity-first cutover."
status: completed
priority: P2
effort: 44h
branch: main
tags: [frontend, react, vite, typescript, performance, packaging]
created: 2026-11-14
---

# React frontend migration

Goal: same UI, same CSS, same behaviour; faster actions, no full sidebar/topbar/status redraw per state event,
lazy heavy libs (ace, xterm-webgl). Old UI stays at `/` until parity; new UI lives at `/ui/` meanwhile.

## Key decisions
- Source: `frontend/` (repo root): package.json, vite.config.ts, tsconfig, `src/`. Build -> `src/herd/web_dist/` (gitignored, hatch `artifacts`).
- Vite `base: "/ui/"`; daemon serves `web_dist` at `/ui/`; `/ui/assets/*` hashed -> `immutable` cache; index.html `no-store`.
- Shared runtime assets stay in `src/herd/web/` at `/static/` (icons/material 3.1MB, vendor/ace 1.7MB, favicon, app-icon): no duplication.
- CSS: the 11 `css/*.css` + `fonts/fonts.css` imported by the entry unchanged (moved to `frontend/src/styles/` only at cutover).
- xterm from npm `@xterm/*` (pinned to vendored major); webgl addon via dynamic `import()`. Ace stays vendored, injected lazily on first editor open.
- State: Zustand. `store.set(raw)` does structural sharing (unchanged panes keep identity) -> `React.memo` rows skip.
- Imperative cores stay plain TS modules outside React: connection, terminal registry, keys, actions, editor.
- Terminal output never touches React state. `<TerminalHost>` only re-parents a long-lived element.
- Cutover (phase 9): `/` serves web_dist; legacy `web/js`, `web/index.html`, vendored xterm deleted.

## Phases

| # | Phase | Effort | Status |
|---|-------|--------|--------|
| 1 | [Scaffold Vite/React/TS + dev proxy](phase-01-scaffold-vite-react-typescript.md) | 3h | completed |
| 2 | [Daemon serving, cache headers, packaging](phase-02-daemon-serving-and-packaging.md) | 3h | completed |
| 3 | [Core modules: connection, Zustand store, theme, keys](phase-03-core-connection-store-theme-keys.md) | 5h | completed |
| 4 | [App shell: sidebar, topbar, status, mobile nav, toasts, modal](phase-04-app-shell-sidebar-topbar-status.md) | 6h | completed |
| 5 | [Overlays: palette, search, new agent, folder picker, dialogs](phase-05-overlays-palette-search-dialogs.md) | 5h | completed |
| 6 | [Views: inbox, tree, machines, settings, server](phase-06-views-inbox-tree-machines-settings-server.md) | 5h | completed |
| 7 | [Files + lazy Ace editor, changes + phone diff](phase-07-files-editor-changes-views.md) | 6h | completed |
| 8 | [Workspace + terminals (xterm, touch scroll, splits)](phase-08-workspace-and-terminals.md) | 8h | completed |
| 9 | [Parity QA, perf check, cutover, docs](phase-09-parity-qa-cutover-and-docs.md) | 5h | completed |

## Dependencies
- 1 -> 2 -> 3 -> 4 -> (5, 6, 7 parallel-safe, distinct files) -> 8 -> 9.
- Overlaps plan `261114-1101-public-browser-access-via-cloud-relay` phase 3 (rewrites `web/js/connection.js`). Decide ordering (see questions).

## Tests
- pytest (238): only `tests/daemon_harness.py` calls `build_app`; no test reads web files. Phase 2 must keep `build_app` working when `web_dist` is absent; adds serving tests.
- Vitest only for pure logic (store derivation/structural sharing, keys mapping, shortPath/ago, modeFor, layout helpers).

## Unresolved questions
1. Relay plan ordering: migrate first (relay targets `connection.ts`) or relay first on vanilla JS?
2. Commit `web_dist` for `pip install git+...` users without Node, or require build (CI builds wheel)? Plan assumes gitignored + hatch artifacts.
3. Keep `/ui/` path forever after cutover (simplest), or rebuild with base `/`? Plan keeps `/ui/` for assets, `/` serves index.
