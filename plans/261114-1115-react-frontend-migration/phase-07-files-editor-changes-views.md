# Phase 07 — Files + lazy Ace editor, Changes + phone diff

## Context Links
- `web/js/views/files-view.js` (201 lines), `web/js/editor.js` (one Ace instance, session per file, dirty tracking, Ctrl+S, beforeunload guard)
- `web/js/views/changes-view.js`, `changes-phone.js` (phone: file list -> full-screen diff), `web/css/changes-phone.css`
- `web/vendor/ace/` (vendored, 38 files, `basePath /static/vendor/ace`)

## Overview
Priority P2. Status completed. Port files tree/editor and changes/diff; Ace loaded only when a file is opened.

## Key Insights
- Today `ace.js` is a sync `<script>` in `<head>` -> blocks first paint for every user. Lazy inject cuts startup.
- Editor is imperative + long-lived (sessions keep undo/unsaved edits across file switches) -> keep editor module outside React; `<AceHost>` re-parents the shared element (same pattern as terminals).
- Keep vendored Ace (no npm ace-builds migration: YAGNI, avoids worker/mode bundling issues). `basePath` stays `/static/vendor/ace`.

## Requirements
- Files: tree with icons (material/minimal sets), open/save/reload-on-disk-change, dirty markers, read-only for non-editable. Editor theme follows app theme. beforeunload warn on dirty.
- Changes: list, worktrees, diff render; phone layout list -> full-screen diff with back.

## Architecture
```
frontend/src/editor/
  load-ace-script.ts     # once-promise: inject <script src=/static/vendor/ace/ace.js>, resolve window.ace
  ace-editor-registry.ts # port of editor.js (async getEditor)
  ace-host.tsx           # mounts shared el, calls layout() on resize
frontend/src/views/files/
  files-view.tsx  file-tree.tsx  file-tree-row.tsx  file-editor-pane.tsx
frontend/src/views/changes/
  changes-view.tsx  changes-file-list.tsx  diff-view.tsx  changes-phone.tsx
frontend/src/types/ace.d.ts   # minimal typing of used Ace API
```

## Related Code Files
- Create: above. Vitest: `modeFor` mapping.

## Implementation Steps
1. load-ace-script (dedup promise, error toast on failure).
2. Port editor.js to registry with async creation; spinner while loading.
3. Port files view (split into tree/editor parts, <200 lines each).
4. Port changes view + phone variant (uses `useIsPhone`).
5. Prefetch Ace on idle once user hovers/opens Files view (optional, only if delay noticeable).

## Todo List
- [x] ace loader + registry + host
- [x] files view parts
- [x] changes + phone diff
- [x] modeFor test (+ parseDiff test)
- [x] parity check desktop/phone (headless Chrome, see report)

## Success Criteria
- Initial load network panel: no ace.js until Files opens a file. Unsaved edits survive switching files and views.

## Risk Assessment
- Ace measuring 0x0 when host hidden -> call `layout()` after attach (as today).
- Global `window.ace` typing -> minimal d.ts.

## Security Considerations
- File contents only in Ace sessions/text nodes; diff lines rendered as text, never innerHTML.

## Next Steps
Phase 08 terminals.
