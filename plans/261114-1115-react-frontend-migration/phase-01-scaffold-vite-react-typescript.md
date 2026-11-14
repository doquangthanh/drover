# Phase 01 — Scaffold Vite + React + TS, dev proxy

## Context Links
- `src/herd/web/index.html` (head order: theme inline script, css links, sync vendor scripts)
- `src/herd/daemon/web_server.py` (routes `/`, `/ws`, `/rpc`, `/health`, `/static/`)
- `src/herd/app_paths.py` (`state_dir()/daemon.json` holds port + token)

## Overview
Priority P1 (blocks all). Status completed. Create `frontend/` project that builds to `src/herd/web_dist/` and a dev
server that proxies the running daemon.

## Key Insights
- Token arrives in `?token=`; `connection.js` stores it in sessionStorage and strips it via `history.replaceState(location.pathname)` -> works under `/ui/` unchanged.
- WS URL built from `location.host` -> through Vite proxy in dev, nothing special needed.
- Theme bootstrap inline script must stay in `<head>` (prevents theme flash).
- Targets: WebView2 (Chromium) + iOS Safari phones -> `build.target: ["es2020", "safari15"]`.

## Requirements
- Functional: `npm run dev` (5173, proxies `/ws` ws:true, `/rpc`, `/static`, `/health` to daemon); `npm run build` -> `src/herd/web_dist/`; `npm run typecheck`; `npm test` (Vitest).
- Non-functional: strict TS; no ESLint/Prettier (YAGNI; `tsc --noEmit` is the gate); deps minimal: react, react-dom, zustand, @xterm/xterm, @xterm/addon-fit, @xterm/addon-web-links, @xterm/addon-webgl; dev: vite, @vitejs/plugin-react, typescript, vitest, @types/react(-dom).

## Architecture
```
frontend/
  index.html            # theme inline script, <div id=app>, <div id=overlay-root>, <div id=toasts>, module entry
  vite.config.ts        # base /ui/, outDir ../src/herd/web_dist, emptyOutDir, proxy from daemon.json
  tsconfig.json
  src/main.tsx          # imports styles, renders <App/>
  src/styles/index.ts   # imports ../../../src/herd/web/fonts/fonts.css + web/css/*.css (same order as old index.html) + @xterm/xterm/css/xterm.css
```
Proxy target: `HERD_DAEMON_URL` env, else read `%LOCALAPPDATA%/herd/daemon.json` (or `HERD_STATE_DIR`) for port; log the `/ui/?token=` dev URL on start.

## Related Code Files
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`, `frontend/index.html`, `frontend/src/main.tsx`, `frontend/src/app.tsx` (placeholder), `frontend/src/styles/index.ts`, `frontend/src/vite-env.d.ts`
- Modify: `.gitignore` (`frontend/node_modules/`, `src/herd/web_dist/`)

## Implementation Steps
1. `npm create vite@latest frontend -- --template react-ts`; strip demo files; pin versions (`npm i -E`).
2. Check vendored xterm version (banner in `web/vendor/xterm.js` / LICENSE) and pin `@xterm/*` to same major.
3. Write `vite.config.ts`: base, outDir, `server.fs.allow: [".."]` (imports CSS from `src/herd/web`), proxy, `build.target`, `test` block for Vitest (environment `node`).
4. Port `<head>` of old index.html: meta viewport `viewport-fit=cover`, theme inline script, favicon `/static/favicon.png`.
5. Style entry imports CSS in old order (fonts, xterm, base, themes, sidebar, workspace, overlays, views, tablet-touch-wide, mobile, mobile-views, mobile-sheets, changes-phone).
6. Root markup must reproduce ids/classes CSS depends on: `#app.win > #sidebar, main#main > #topbar.tabs, #workspace.body, #altview.altview, #statusbar.status`, `#overlay-root`, `#toasts`, `#conn-banner`.
7. Verify `npm run build` output and `npm run dev` against a running daemon.

## Todo List
- [x] scaffold + pin deps
- [x] vite.config.ts (base, outDir, proxy, fs.allow, target, vitest)
- [x] index.html + styles entry
- [x] .gitignore
- [x] build + dev smoke test

## Success Criteria
- `npm run build` writes `src/herd/web_dist/index.html` + `assets/*-[hash].js|css` (fonts hashed too).
- Dev server page connects to daemon websocket (devtools shows `/ws` 101).

## Risk Assessment
- Vite refusing files outside root -> `server.fs.allow`. Font `url()` in fonts.css rewritten by Vite (expected, fonts become hashed assets).
- Hook blocks `node_modules` in bash -> use npm scripts only, never path into it.

## Security Considerations
- Dev proxy binds localhost only (`server.host` default). Never print token into committed files; daemon.json read at runtime only.

## Next Steps
Phase 02 serves the build from the daemon.
