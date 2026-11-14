# Changelog

## Unreleased
### Changed
- Web UI rewritten as Vite + React + TypeScript + Zustand (`frontend/`). Same layout, CSS and shortcuts; the sidebar,
  top bar and status bar no longer rebuild on every state event, Ace and the xterm WebGL addon load lazily.
- `/` now serves the built UI from `src/herd/web_dist/` (also reachable at `/ui/`); hashed assets are cached as immutable,
  `index.html` stays `no-store`. Missing build answers `503 UI not built`.
- Building from source needs Node 20.19+ or 22+: `npm --prefix frontend ci && npm --prefix frontend run build`.
- `packaging/herd.spec` bundles `web_dist/` and fails fast when it is missing; the wheel includes it via hatch `artifacts`.

### Removed
- Legacy vanilla-JS UI (`src/herd/web/js`, `index.html`) and vendored xterm files (xterm now comes from npm `@xterm/*`).
- CSS and fonts moved to `frontend/src/styles/` (content unchanged).

### Fixed
- Layout tree type in the frontend matches the daemon (`split`, not `dir`).
