# Phase 08 — Workspace + terminals (most careful)

## Context Links
- `web/js/terminals.js` (registry Map paneId->{el, term, fit}; DA-response filter; replay reset; ResizeObserver + 60ms debounced fit -> `pane.resize`; font-ready refit; WebGL only for fine pointers; disposeMissing)
- `web/js/terminal-touch-scroll.js` (drag scroll, momentum, alt-buffer arrow keys, jump-to-latest)
- `web/js/workspace.js` (split tree, draggable gutters -> `tab.set_layout`, pane header, keybar + compose, stopped-pane card, welcome card, `refreshPaneHeaders`)
- `web/js/app.js::workspaceKey/updateFocusClasses`

## Overview
Priority P1. Status completed (real-phone test still open). Terminal must never re-render on state events; input latency must be equal or better than legacy.

## Key Insights
- Output path stays `ws.onmessage -> outputHandlers.get(pane) -> term.write` (no React). Input path `term.onData -> conn.input` (no React).
- xterm element created once per pane by registry; React only re-parents it. Moving a pane in the split tree remounts `<TerminalHost>` -> appendChild of same element; xterm survives; re-focus if it had focus (as `renderWorkspace` does).
- Gutter drag mutates `style.flex` via refs during pointermove; commit layout via rpc on pointerup only (no state per move).
- WebGL addon: `import("@xterm/addon-webgl")` after `term.open`, skipped on `(pointer: coarse)`; this removes 100KB from initial load.
- `disposeMissing` driven by a store subscription on pane id set (not by render).

## Requirements
- Parity: replay reset, DA filter, resize rpc dedupe by size, font refit, theme change applies to all terms, prefix keys via `attachCustomKeyEventHandler(handleKey)`, find in scrollback, copy selection, keybar keys/paste/compose, zoom, split right/down, focus classes `.pane.focus` / `.slot.has-focus`, stopped card (resume/fresh/close), welcome card, phone font 12px.
- Perf: zero React commits touching `<TerminalHost>` on `state`/`pane`/`status` events (verify with Profiler).

## Architecture
```
frontend/src/terminal/
  terminal-registry.ts      # port of terminals.js (getTerminal, focusTerminal, disposeMissing, findInPane, copySelection, sendToPane)
  terminal-fit.ts           # scheduleFit, font-ready refit, lazy webgl
  terminal-touch-scroll.ts  # 1:1 port (typed)
  terminal-host.tsx         # memo({paneId}); useLayoutEffect append/remove el; no store subscription
frontend/src/workspace/
  workspace.tsx             # tab layout or welcome; zoom handling
  split-node.tsx            # recursive, key = pane id / path; gutter-drag via refs
  pane-frame.tsx            # memo; subscribes to its pane only; header + find bar + host + keybar
  pane-header.tsx  pane-keybar.tsx  stopped-pane-card.tsx  welcome-card.tsx
```
Focus classes: `pane-frame` selects `s.ui.focusedPane === paneId` (boolean selector -> only 2 frames re-render on focus change; host untouched).

## Related Code Files
- Create: above. Modify: actions (focusPane/zoom/split/find/copy use registry), overlays find bar.

## Implementation Steps
1. Port registry/fit/touch-scroll with npm `@xterm/*` imports (named classes instead of globals).
2. TerminalHost + store subscription for disposal.
3. Workspace/split/pane components; gutter drag via refs.
4. Wire actions + keys + find bar + compose.
5. Measure: React Profiler during agent output burst and status flips; keystroke echo latency vs legacy (Chrome perf trace, same pane, 20 keystrokes).
6. Test on real phone (touch scroll, keyboard pop, landscape) and pywebview desktop.

## Todo List
- [x] registry + fit + lazy webgl
- [x] touch scroll port
- [x] TerminalHost + disposal subscription
- [x] workspace/split/pane/header/keybar/stopped/welcome
- [x] actions wiring (zoom, split, find, copy, focus)
- [x] profiler + latency measurement
- [~] phone (CDP touch emulation) + desktop verified; real phone + pywebview not tested

## Success Criteria
- Profiler: no TerminalHost commits during events. Latency not worse than legacy. All workspace behaviours in parity checklist pass.

## Risk Assessment
- StrictMode double-mount in dev attaching twice -> registry idempotent (`getTerminal` returns existing; `attach` guarded by Set). Host cleanup only detaches el, never disposes.
- Remount on layout change losing focus/scroll -> capture `hadFocus` before commit, refocus after (useLayoutEffect).
- WebGL cell-size change after first fit -> keep `onChangeTextureAtlas -> scheduleFit`.
- npm xterm version differing from vendored -> pin same major; retest touch-scroll selectors (`.xterm-screen`).

## Security Considerations
- web-links addon opens links in new window with `noopener` (default handler); keep.

## Next Steps
Phase 09 cutover.
