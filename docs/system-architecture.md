# System architecture

```
drover.exe (pywebview window) / browser
        |  http://127.0.0.1:<port>/?token=...
        v
drover-server (aiohttp daemon, src/drover/daemon)
  /            index.html of the React build (no-store)      src/drover/web_dist/   (built, gitignored)
  /ui/         same index (kept so old links and the dev server path work)
  /ui/assets/  hashed JS/CSS/fonts, `immutable` cache
  /static/     shared runtime files: icons/material, vendor/ace, favicon, app-icon    src/drover/web/
  /ws /rpc     token-protected state stream + JSON-RPC (unchanged)
  503 "UI not built" when web_dist is missing (daemon, CLI and tests still work)
```

## Frontend (`frontend/`, Vite + React 19 + TypeScript + Zustand)

- `src/core/`: imperative, React-free modules: `connection` (ws + rpc), `store` (Zustand, structural sharing so unchanged
  panes keep identity), `keys` (Ctrl+B prefix), `theme`, `file-icons`, `event-router`.
- `src/terminals/`: xterm registry. Terminal output never touches React state; `TerminalHost` only re-parents a long-lived element.
- `src/shell/` (sidebar, topbar, status bar, mobile nav, toasts), `overlays/` (palette, search, dialogs), `views/`,
  `files/` (tree + Ace, Ace injected from `/static/vendor/ace` on first open), `changes/`, `workspace/` (splits, panes).
- Views register through `views/view-registry` and are lazy chunks; xterm webgl is a dynamic import.
- `src/styles/`: the original plain CSS files, global (shared class names), imported in cascade order by `styles/index.ts`.
- Rendering rule: components subscribe with narrow selectors (`useStore(s => ...)`) and rows are `React.memo`, so a state
  event re-renders only what changed.

Build: `npm --prefix frontend run build` writes `src/drover/web_dist/` (`base: "/ui/"`). Dev: `npm --prefix frontend run dev`
proxies `/ws /rpc /static /health` to the running daemon. Packaging: `packaging/drover.spec` bundles `web/` and `web_dist/`
and refuses to build when `web_dist` is missing; the hatch wheel includes it via `artifacts`.
