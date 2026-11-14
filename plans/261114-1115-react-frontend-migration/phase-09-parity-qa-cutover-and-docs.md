# Phase 09 — Parity QA, perf check, cutover, docs

## Context Links
- `src/herd/daemon/web_server.py`, `src/herd/daemon/daemon_client.py::ui_url` (`/?token=`), `packaging/herd.spec`, `README.md` (web UI + phone layout sections, xterm license line), `docs/` (does not exist yet)

## Overview
Priority P1. Status completed. Verify parity, switch `/` to new UI, delete legacy code, document.

## Key Insights
- `ui_url` keeps `/?token=` -> after cutover `/` serves `web_dist/index.html`; assets under `/ui/assets/`. No desktop launcher change.
- Shared static assets (icons, ace, favicon, app-icon) remain in `src/herd/web/` -> `web_static_dir()` meaning unchanged.

## Requirements
- Parity checklist (desktop window, desktop browser, tablet, landscape phone, portrait phone): every item in task brief (layouts, touch scroll, mobile nav/sheets, prefix shortcuts, palette, search, new agent, folder picker, editor, changes/diff, inbox, tree, machines, settings, server, themes, restore dialog) + toasts, reconnect banner, remote machine panes.
- Perf evidence: first load bytes/time before vs after; events -> re-render counts; keystroke latency.

## Architecture
After cutover:
```
frontend/src/styles/*.css     # git mv from src/herd/web/css (content unchanged) + fonts.css
src/herd/web/                 # favicon.png, app-icon.ico, fonts/ (woff2 only if still referenced), icons/, vendor/ace/
src/herd/web_dist/            # build output (gitignored)
```
`/` and `/ui/` both -> web_dist index; fallback 503 message if not built.

## Related Code Files
- Modify: `web_server.py` (index route -> dist), `frontend/src/styles/index.ts`, `vite.config.ts` (drop fs.allow), `README.md`, `.gitignore`, `packaging/herd.spec` comment
- Delete: `src/herd/web/index.html`, `src/herd/web/js/**`, `src/herd/web/vendor/xterm.js`, `addon-*.js`, `xterm.css` (keep `LICENSE-xterm.txt` -> move to frontend or keep; update README path)
- Create: `docs/system-architecture.md` frontend section (or README section), `docs/project-changelog.md` entry, `docs/code-standards.md` frontend rules (if docs/ adopted)

## Implementation Steps
1. Run parity checklist on `/ui/`; fix gaps.
2. Collect perf numbers (Lighthouse/devtools) legacy vs new; note in report.
3. Switch index route; update tests from phase 2 (`/` serves dist).
4. Delete legacy files; move css; rebuild; full pytest + typecheck + vitest.
5. Build PyInstaller bundle (`npm --prefix frontend ci && npm --prefix frontend run build && uv run pyinstaller packaging/herd.spec --noconfirm`), launch herd.exe, smoke test.
6. Docs: README dev workflow (`npm run dev`, proxy, `/ui/?token=`), build prerequisites, license path; docs-manager updates docs/.

## Todo List
- [x] parity checklist all form factors
- [x] perf comparison
- [x] cutover route + tests
- [x] delete legacy, move css
- [x] packaged exe smoke test
- [x] README + docs

## Success Criteria
- All checklist items pass; pytest/vitest/typecheck green; packaged exe works offline; legacy code gone.

## Risk Assessment
- Hidden behaviour missed -> keep legacy deletion in a separate commit (easy revert).
- Users with stale cached index -> index is no-store; hashed assets immutable.

## Security Considerations
- No new endpoints; token handling unchanged. Consider CSP header on index later (relay plan wants it; inline theme script would need hash).

## Next Steps
Relay plan phase 3 targets `frontend/src/core/connection.ts`.
