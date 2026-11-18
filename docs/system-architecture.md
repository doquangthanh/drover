# System architecture

Linux release bundle (`~/.local/share/drover`): Python `dr` (CLI + TUI, PyInstaller) + Rust `drover` (Tauri window,
`rust/crates/drover-desktop`) + Rust `drover-server` (daemon, `rust/crates/drover-daemon`, binary of `drover-cli`).
`dr server run` execs `drover-server` when it sits next to `dr` (`DROVER_ENGINE=python` keeps the Python daemon).
Both daemons speak the same `/ws` + `/rpc` protocol and share `daemon.json`, `session.json`, `chats/`, so either can
take over the other's session. Windows still ships the all-Python `drover.exe`.

```
drover (Tauri window) / drover.exe (pywebview, Windows) / browser
        |  http://127.0.0.1:<port>/?token=...
        v
drover-server (Rust: tokio + axum; Python fallback: aiohttp, src/drover/daemon)
  /            index.html of the React build (no-store)      src/drover/web_dist/   (built, gitignored)
  /ui/         same index (kept so old links and the dev server path work)
  /ui/assets/  hashed JS/CSS/fonts, `immutable` cache
  /static/     shared runtime files: icons/material, vendor/ace, favicon, app-icon    src/drover/web/
  /ws /rpc     token-protected state stream + JSON-RPC (unchanged)
  503 "UI not built" when web_dist is missing (daemon, CLI and tests still work)
```

## TUI client (`src/drover/tui/`, Textual, optional extra `tui`)

`dr tui` is one more websocket client of the daemon (same `/ws` protocol as the web UI and `dr attach`). No daemon change.

```
TuiApp
 +- DaemonConnection (aiohttp ws, rpc futures, reconnect + re-attach)      daemon_ws_connection.py
 +- WorkspaceSidebar (Tree: space > tab > pane + state glyph)              workspace_sidebar.py
 +- SplitLayoutView (tab.layout -> nested Horizontal/Vertical)             split_layout_view.py
 |    +- TerminalPaneView xN (pyte screen + Line API, keys -> {"t":"in"})   terminal_pane_view.py, terminal_emulator_screen.py
 +- PrefixKeyRouter (Ctrl+A + key -> action)                               prefix_key_router.py, tui_app_actions.py
 +- RestoreStoppedDialog (session.resume / session.discard)                restore_stopped_dialog.py
```

- Terminal bytes (`out`/`replay`) go straight from the connection to the pane view; structure events (`state`,
  `status`, `pane`) become Textual messages and are coalesced into one refresh per 100 ms.
- Visible live panes are attached, hidden ones (zoom, narrow terminal, other tab) are detached.
- Layout modes by terminal size (`responsive_mode.py`): wide >= 100 columns (docked sidebar), medium 60-99
  (sidebar overlay on prefix `b`), narrow (< 60 columns or < 15 rows: one pane at a time).
- Ctrl+Q is delivered to the pane (Textual would quit); quit is prefix `d`.

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
