# Phase 06 — Views: inbox, tree, machines, settings, server

## Context Links
- `web/js/views/inbox-view.js`, `inbox-side-panel.js`, `rule-tester.js`, `tree-view.js`, `machines-view.js`, `settings-view.js`, `appearance-panel.js`, `server-view.js`
- `web/js/app.js` (`LIVE_VIEWS` = inbox; `machinesChanged()` avoids redraw while typing)

## Overview
Priority P2. Status completed (not yet browser-verified; see phase 9 QA). Port alt-views rendered into `#altview`.

## Key Insights
- Old special-casing (inbox live, machines redraw only on key change and never while an input is focused) becomes free in React: controlled inputs keep local state, selectors decide re-render.
- Views fetch data via rpc on open -> `useEffect` + local state; small `useRpc(method, params, deps)` hook (DRY) with loading/error.
- Settings/server views use `window.pywebview.api.open_path` when available.

## Requirements
- Feature parity incl. inbox allow/deny policy prompts, rule tester, tree navigation, machines add/remove/connect status + latency, settings (prefix, theme, icon set, appearance), server info/restart.

## Architecture
```
frontend/src/views/
  alt-view-host.tsx (view switch -> component, lazy() per view for smaller initial bundle)
  inbox-view.tsx  inbox-side-panel.tsx  rule-tester.tsx
  tree-view.tsx  machines-view.tsx  machine-row.tsx
  settings-view.tsx  appearance-panel.tsx  server-view.tsx
frontend/src/core/use-rpc.ts
```

## Related Code Files
- Create: above. Modify: `frontend/src/app.tsx` (mount alt-view-host).

## Implementation Steps
1. `use-rpc` hook (+ errorToast on failure).
2. Port each view, keep markup/classes; split files exceeding 200 lines.
3. `React.lazy` per view with tiny fallback (views are not first paint).
4. Side-by-side check vs legacy, desktop + phone.

## Todo List
- [x] use-rpc (views/use-rpc.ts)
- [x] inbox (+side panel, rule tester)
- [x] tree, machines
- [x] settings (+appearance), server
- [x] lazy loading (register.ts)
- [ ] side-by-side parity check (phase 9)

## Success Criteria
- Typing in machines form not interrupted by machine status events. Inbox updates live. All view actions work.

## Risk Assessment
- Lazy chunk flash on first open -> acceptable; prefetch on idle if noticeable (only if measured).

## Security Considerations
- Rule tester regex input stays server-side evaluated as before; render results as text.

## Next Steps
Phase 09 parity checklist covers these views.
