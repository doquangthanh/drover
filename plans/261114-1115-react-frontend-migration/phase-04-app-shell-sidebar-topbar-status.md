# Phase 04 — App shell: sidebar, topbar, status, mobile nav, toasts, modal, actions

## Context Links
- `web/js/app.js` (render loop, view switch, `pane-open` body class, conn banner)
- `web/js/sidebar.js`, `workspace.js::renderTopbar/renderStatus`, `topbar-views.js`, `mobile-nav.js`, `mobile-topbar.js`, `mobile-dictate.js`
- `web/js/actions.js` (170 lines, all user actions), `modal.js`, `dom.js::toast/topExtra`

## Overview
Priority P1. Status completed (2026-11-14; side-by-side visual diff vs legacy not done, see report). Static frame of the app in React; workspace area is a placeholder until phase 8 (old UI still at `/`).

## Key Insights
- Old app rebuilds DOM for sidebar/topbar/status on every event; React + narrow selectors updates only changed rows.
- `topExtra` (views push meta/right content into topbar) -> small zustand slice or React context set by views.
- `actions` used by keys, palette, buttons -> plain module `buildActions()` using `getState()`; `forceWorkspace/refreshView` hacks disappear (React re-renders by data).
- `prompt/confirm` are promise-based -> modal store holding one active modal + resolver; render into `#overlay-root` via portal.

## Requirements
- Identical markup classes as old renderers (CSS untouched). Sidebar collapse, space/tab select, rename (dblclick), close, new agent button, zoom indicator, view bar for non-workspace views, mobile back/more buttons, status bar counts/branch chip/prefix indicator, conn banner, toasts (6s auto-dismiss, click action), `body.pane-open` toggle.
- Layout switch (phone <-> desktop) re-renders via `useIsPhone`.

## Architecture
```
frontend/src/app.tsx                  # shell layout, view switch, body class effect, connect on mount
frontend/src/actions/                 # split from actions.js (<200 lines each)
  build-actions.ts  pane-actions.ts  tab-space-actions.ts  view-actions.ts
frontend/src/shell/
  sidebar.tsx  sidebar-space-row.tsx  sidebar-pane-row.tsx (React.memo)
  topbar.tsx  topbar-tabs.tsx  topbar-view-bar.tsx  status-bar.tsx
  mobile-nav.tsx  mobile-topbar.tsx  mobile-dictate.tsx
  toasts.tsx  conn-banner.tsx
frontend/src/overlays/modal-host.tsx + modal-store.ts (openModal/promptText/confirmBox/closeModal)
```

## Related Code Files
- Create: files above. Modify: none legacy.

## Implementation Steps
1. Port actions to TS modules; wire `registerActions` (keys.ts).
2. Modal store + host (focus trap/escape same as modal.js).
3. Shell components, one per old renderer; copy class names exactly; memo rows keyed by id.
4. topExtra slice; views set it via effect.
5. Toasts + conn banner from store.
6. Manual check on desktop, tablet, phone widths (devtools) against old UI side by side.

## Todo List
- [x] actions modules
- [x] modal store/host
- [x] sidebar, topbar, status, view bar
- [x] mobile nav/topbar/dictate (DictateButton ready, placed by phase 8)
- [x] toasts, banner, body class
- [ ] visual diff vs legacy at 3 widths (checked desktop 1280 + phone 390 render only; no side-by-side)

## Success Criteria
- React DevTools "highlight updates": a `status`/`pane` event re-renders only affected row + status bar.
- Pixel-equivalent shell at desktop/tablet/phone vs legacy.

## Risk Assessment
- Class/DOM structure drift breaks CSS -> copy structure from `h()` calls literally; compare with screenshots.
- Global keydown capture order vs React handlers -> keep listener in keys.ts (capture phase), as today.

## Security Considerations
- Text rendered via JSX (escaped). Remove `html:` usages except trusted icon constants.

## Next Steps
Phases 05/06/07 can run in parallel (distinct dirs: overlays/, views/, files/).
