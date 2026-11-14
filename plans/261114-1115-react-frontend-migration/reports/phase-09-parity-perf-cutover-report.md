# Phase 9 report: parity, performance, cutover

Method: one scratch daemon (temp state/config dirs, 2 spaces, 4 panes, git repo with changes), headless Chrome 157 over CDP.
Old `/` vs new `/ui/` (before cutover), widths 1400 / 820 (touch) / 390 (phone, mobile+touch). Per scene: normalized DOM
signature (tag, classes, aria/role/title/href, text with digits masked; xterm/ace/svg internals skipped) + screenshot pixel diff.
Terminals, ".t" ages hidden in screenshots. Dynamic old-UI edits by someone else during the run (logo markup) were re-run.

## Parity checklist

| Item | Desktop | Tablet | Phone | Result |
|---|---|---|---|---|
| workspace (splits, panes, sidebar, topbar, status bar) | 0.00% px, DOM same | same | same | pass |
| inbox / tree / machines / files / changes / settings / server | same | same | same (via bottom nav + More sheet) | pass |
| files: open file (tree + editor), changes: select file / phone file list then full-screen diff | same | same | same | pass |
| dialogs: palette, search, new agent, shortcuts, broadcast, folder picker, new space picker | same | same | same (as sheets) | pass |
| sidebar hidden, mobile nav, More sheet, FAB | same | same | same | pass |
| themes dark / light / midnight | 0.00% | 0.00% | 0.00% | pass |
| (a) Files topbar shows only "Terminals" button | identical to old (old does the same) | | | pass (no change needed) |
| (b) `.split.row{align-items:stretch}` | present in styles/workspace.css | | | pass |
| (c) duplicate file-icon component | merged into `files/file-icon.tsx` (optional `set` prop), `views/sample-file-icon.tsx` deleted | | | fixed |
| (d) Tab.layout node type | `{split?: "row"\|"col"}` (was `dir`), test fixture fixed | | | fixed |
| leftover "view arrives in migration phases" placeholder rendered into hidden #altview | removed | | | fixed |

Behaviour checks (func script, same on both UIs after a reset; run on `/` after cutover too): palette filter + run,
search + enter, sidebar toggle, split right/down, terminal typing reaches the pane, zoom, new tab, rename, new agent
submit, Ace editor open/edit/Ctrl+S writes file, changes list + diff, settings, tree, shortcuts, Escape closes dialog,
close pane: all pass on new. Restore dialog ("Pick up where you left off?") after daemon restart: shown identically.
No console errors / exceptions in any run (0).

Remaining DOM differences (accepted, not regressions):
1. Modals carry `tabindex=-1` in new (focus management; harmless).
2. Phone/tablet Inbox: new renders the settings button + "Jump to a terminal" search that `mobile-views.css` is written for;
   the old UI dropped them when switching to Inbox via the tab bar (3.4% pixel diff on that one phone screen). New matches the CSS intent.
3. React keeps an empty body-level `div` (root) and `display:contents` anchor wrappers around terminals (no layout effect).
4. `has-focus` class set on `.split` nodes by new (old only sets it on slots); CSS only targets `.split > .slot:not(.has-focus)`.

## Performance (scratch daemon, production build, Chrome cache disabled for cold, 7 runs, median; before cutover)

| Metric | Old `/` | New `/ui/` | Delta |
|---|---|---|---|
| Cold: requests | 59 | 10 | -83% |
| Cold: bytes transferred | 1175 KB | 808 KB | -31% |
| Cold: DOMContentLoaded | 493 ms | 245 ms | -50% |
| Cold: load | 497 ms | 250 ms | -50% |
| Cold: sidebar visible (first agent row) | 622 ms | 466 ms | -25% |
| Warm: requests | 58 | 9 | -84% |
| Warm: DOMContentLoaded | 101 ms | 48 ms | -53% |
| Warm: load | 104 ms | 50 ms | -52% |
| Warm: sidebar visible | 166 ms | 135 ms | -19% |
| DOM mutation records per state event (20 pane.rename events) | 9.1 (561 nodes added+removed total) | 2.0 (0 nodes added/removed) | -78% records, no node churn |

New is faster on every number. Note: sidebar-visible waits for the first websocket state frame; in new it arrives ~215 ms
after `load` (vs ~125 ms in old) because the app mounts after the bundle executes, but it is still earlier overall.
Cold bytes: new includes xterm + React in the main chunk (583 KB, 161 KB gzip) but does not ship Ace/webgl until needed.
Long tasks during the event burst: 0 ms in both. Not measured: keystroke latency (terminal input path is unchanged
xterm -> ws), Lighthouse.

## Cutover

- `/` and `/ui/` both serve `web_dist/index.html` (no-store); `/ui/assets/*` immutable; `/static/` keeps icons, ace, favicon,
  app-icon, xterm license. Missing build: 503 "UI not built: cd frontend && npm run build" on `/`, `/ui/`, `/ui/index.html`.
- Deleted: `src/herd/web/index.html`, `src/herd/web/js/**` (35 files), `web/vendor/{xterm.js,xterm.css,addon-fit.js,addon-web-links.js,addon-webgl.js}`.
- Moved (content unchanged, working-tree state at move time): `web/css/*.css` (11) and `web/fonts/` -> `frontend/src/styles/`
  (+ `fonts/`); `styles/index.ts` imports updated; vite `fs.allow` dropped; fonts are bundled as hashed assets.
- pytest 245 pass (tests updated: `/` served/503/no-store); vitest 81 pass; typecheck clean; build ok.

## Packaging

PyInstaller 6.22.3 ran here: `--distpath/--workpath` under Temp, exit 0. Built `hd.exe server run` against scratch state:
`/` 200 no-store, `/ui/` 200, `/ui/assets/index-*.js` 200 immutable, `/static/favicon.png`, `/static/icons/material/map.json`,
ace.js 200; bundle contains `_internal/herd/web_dist` (23 files) and `web` (icons/ace). Not run: `herd.exe` (WebView2 window)
and rendering inside the packaged window. Repo `build/`, `dist/` and the installed herd were not touched; temp output deleted.

## Not verified
- pywebview desktop window (WebView2), real touch device (touch scroll, on-screen keyboard, dictate), landscape phone.
- Reconnect banner (both UIs showed no banner 4 s after `server.stop`; could not differentiate), toasts from real agent events,
  remote-machine panes, blocked-agent states (no agent CLIs used, only shells).
- Ace dirty-state / multi-tab editing beyond open-edit-save; settings write; machines add.
- Keystroke latency, Lighthouse.

## Note on concurrent edits
Another session changed the old UI's logo (sidebar.js `role="img"`, sidebar.css/mobile.css, favicon/app icons) mid-run. The React
`sidebar.tsx` already matched; the CSS moved to `frontend/src/styles/` includes those edits.
