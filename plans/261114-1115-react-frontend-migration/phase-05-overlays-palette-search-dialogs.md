# Phase 05 — Overlays: palette, search, new agent, folder picker, dialogs

## Context Links
- `web/js/palette.js`, `search.js`, `new-agent.js`, `folder-picker.js` (pywebview `pick_folder` bridge), `views/shortcuts-dialog.js` (shortcuts + broadcast), `views/server-view.js::maybeShowRestore`, `find-bar.js`

## Overview
Priority P2. Status completed (browser/pywebview check pending, see phase 9). Port every modal/overlay onto the phase-4 modal host.

## Key Insights
- All overlays are modal content + local input state -> natural React components with local `useState`; no store churn while typing.
- Folder picker: prefers `window.pywebview.api.pick_folder` in desktop window, else in-app browser (`fs.*` rpc). Keep both paths.
- Restore dialog is triggered from event-router on state (once per session) -> keep "shown once" flag in module scope.
- Find bar lives inside a pane (phase 8 mounts it) but its component is built here; calls `findInPane` from terminal registry (stub until phase 8).

## Requirements
- Palette: fuzzy filter over actions + panes, keyboard nav, Enter runs. Search: jump to terminal. New agent: folder, agent kind, worktree option, machine select. Shortcuts dialog renders `SHORTCUTS`. Broadcast to selected panes. Restore dialog: resume/fresh/discard.
- Same keyboard behaviour (Esc closes, arrows, Enter).

## Architecture
```
frontend/src/overlays/
  command-palette.tsx  terminal-search.tsx  new-agent-dialog.tsx  new-agent-form-fields.tsx
  folder-picker-dialog.tsx  folder-picker-desktop-bridge.ts  shortcuts-dialog.tsx  broadcast-dialog.tsx
  restore-dialog.tsx  pane-find-bar.tsx  use-list-keyboard-nav.ts (shared up/down/enter hook, DRY palette+search+picker)
frontend/src/types/pywebview.d.ts     # window.pywebview?.api typing
```

## Related Code Files
- Create: above. Modify: `frontend/src/actions/*` (palette/search/newAgent open functions call modal store).

## Implementation Steps
1. Shared `use-list-keyboard-nav` hook.
2. Port each overlay; keep class names; open functions return promises where old ones did.
3. Wire actions + keys (`:`, `/`, `c`, `C`, `?`, `B`).
4. Verify in pywebview (`herd` desktop pointed at `/ui/`) that native folder dialog still works.

## Todo List
- [x] list-nav hook
- [x] palette, search
- [x] new agent + folder picker (both paths)
- [x] shortcuts, broadcast, restore, find bar
- [x] actions wiring (register.ts)
- [ ] manual keyboard + pywebview native-folder test in a real browser (not done; phase 9 QA)

## Success Criteria
- Every prefix shortcut opening an overlay works in new UI; dialogs look identical; phone sheet styles apply.

## Risk Assessment
- Focus restoration to terminal after closing overlay -> modal host calls `focusTerminal(focusedPane)` on close (phase 8 registry; no-op before).

## Security Considerations
- Paths from fs rpc rendered as text only. pywebview bridge only exposes existing harmless methods.

## Next Steps
Phase 08 mounts find bar in panes.
