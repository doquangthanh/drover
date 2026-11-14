# Phase 03 — Core modules: connection, Zustand store, theme, keys

## Context Links
- `web/js/connection.js` (rpc/attach/detach/input/reattachAll, 1.5s reconnect)
- `web/js/store.js` (raw + ui, merges `machines[].snapshot`, `fixSelection`, `counts`)
- `web/js/app.js::onEvent` (state/resync/pane/status/policy handling)
- `web/js/theme.js`, `file-icons.js`, `viewport.js`, `keys.js`, `dom.js` (helpers, icon PATHS, kindIcon, stateMark, ago, shortPath)

## Overview
Priority P1. Status completed. Typed, framework-free core + Zustand store with cheap selectors. Root of perf win.

## Key Insights
- Today every `state` event = full `raw` replace -> `renderNow` rebuilds sidebar/topbar/status/mobile nav. Fix: structural sharing on `set(raw)` so unchanged spaces/tabs/panes keep object identity; derived lists recomputed once per update (not per getter call: old `store.panes` re-concatenates on every access).
- `keys.js` and `terminals.js` call into store imperatively -> use `useStore.getState()` / `setState`, not hooks.
- `upsertPane` mutates arrays in place -> replace with immutable update.

## Requirements
- Same wire protocol; same token handling; same reconnect behaviour; `onConnection` -> `connected` flag in store.
- Store API: `raw`, `ui` (view, tabId, spaceId, sidebar, prefix, findPane, focusedPane, mobilePane), derived `{spaces, tabs, panes, stopped, paneById, tabById, spaceById, counts}`; actions `setRaw`, `upsertPane`, `setUi(patch)`.
- `fixSelection` semantics identical.

## Architecture
```
frontend/src/core/
  protocol-types.ts        # RawState, Pane, Tab, Space, Machine, Layout node, event names
  connection.ts            # port of Connection class (typed), exported singleton `conn`
  structural-share.ts      # replaceEqual(prev, next): reuse prev objects that are deep-equal (~40 lines)
  store.ts                 # zustand create(); setRaw -> share -> derive -> fixSelection
  store-derive.ts          # merge local + machines snapshots, index maps, counts
  event-router.ts          # port of app.js onEvent (state/resync/pane/status/policy) -> store + toasts
  theme.ts, file-icons.ts, viewport.ts (+ useIsPhone hook via useSyncExternalStore)
  keys.ts                  # SHORTCUTS, handleKey, setPrefix; window keydown capture listener
  format.ts                # ago, shortPath
frontend/src/ui/atoms/     # icon.tsx (PATHS), kind-icon.tsx, state-mark.tsx, branch-chip.tsx, space-avatar.tsx
```
Component rule: subscribe with narrow selectors (`useStore(s => s.paneById.get(id))`, `useShallow` for lists of ids).

## Related Code Files
- Create: files above + `frontend/src/core/*.test.ts` (structural-share, store-derive/fixSelection, keys mapping, format)
- Modify: none in Python. Legacy JS untouched.

## Implementation Steps
1. Define protocol types from `combined_state()` shape (read `src/herd/core/state_store.py` / daemon_context) and existing JS usage.
2. Port connection.ts 1:1 (class, typed pending map, output handlers map stays outside React).
3. structural-share + derive + store; Vitest: unchanged pane keeps identity after new raw; machine-prefixed panes merged; fixSelection cases.
4. Port theme/file-icons/viewport with listener sets (unchanged logic); `useIsPhone` hook.
5. Port keys.ts; `registerActions` stays (actions filled in phase 4).
6. Port event-router; toasts via a tiny toast store (phase 4 renders it).
7. `npm run typecheck && npm test`.

## Todo List
- [x] protocol-types
- [x] connection.ts
- [x] structural-share + store + derive (+tests)
- [x] theme / file-icons / viewport
- [x] keys.ts (+tests)
- [x] event-router
- [x] atoms + format (+tests)

## Success Criteria
- Typecheck + Vitest green. Placeholder app shows live pane count from store over real daemon.
- Test proves identity reuse for unchanged entities.

## Risk Assessment
- Deep-equal cost on large state: state is small (tens of panes); compare per entity, early-exit. Measure once.
- Missing fields in types -> use `?` liberally; types document reality, not enforce.

## Security Considerations
- Token only in sessionStorage + ws query (as today). No `dangerouslySetInnerHTML` except static icon SVG paths (trusted constants).

## Next Steps
Phase 04 shell consumes store + actions.
