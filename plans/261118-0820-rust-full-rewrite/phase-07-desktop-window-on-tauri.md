# Phase 07: Desktop window on Tauri

## Context Links
- `src/drover/desktop/*`, `packaging/drover_entry.py`, `frontend/` (unchanged code), `frontend/daemon-target.ts`

## Overview
- Priority: P1. Status: in progress (window works; memory result in reports/phase-07-tauri-window-memory.md). Effort: 14h.
- Replace pywebview + PyQt6/QtWebEngine with Tauri v2 (system webview: WebKitGTK on Linux, WebView2 on Windows).

## Key Insights
- The window only shows `http://127.0.0.1:<port>/?token=...`; no Python logic lives in the window except launch,
  single-instance, icons, notifications click-through.
- Today several drover windows run at once (~300 MB each): add single-instance so a second launch focuses the first.

## Requirements
- `drover` binary: ensure daemon, open window at daemon URL, single instance (`tauri-plugin-single-instance`),
  window state remember, tray/icon, `drover` with no args opens the window (changelog 0.1.33 behaviour).
- No frontend code change; if a webview API differs (clipboard, fonts list), handle in daemon or with a tiny shim.

## Architecture
```
drover (Tauri) ── ensure daemon (same lib as dr) ── WebView -> http://127.0.0.1:port/?token
```

## Related Code Files
- Create: `rust/crates/drover-desktop/{Cargo.toml, tauri.conf.json, src/main.rs, icons/}`
- Delete later (phase 09): `src/drover/desktop/*`, PyQt bits in `packaging/drover.spec`.

## Implementation Steps
1. Minimal Tauri window loading the daemon URL.
2. Single instance + focus; window state.
3. Measure: RSS of window + webview processes; xterm.js WebGL FPS on WebKitGTK with 4 busy panes.
   If WebGL is poor on WebKitGTK, fall back to xterm canvas renderer on Linux.
4. Check clipboard, IME (ibus is running on this machine), font list, file drop.

## Todo List
- [x] window loads UI (screenshot checked: sidebar, git branch, agents, terminal)
- [x] single instance (second launch exits in 0.09 s, focuses the first)
- [x] memory measured: [reports/phase-07-tauri-window-memory.md](reports/phase-07-tauri-window-memory.md) — not lighter than Qt on Linux; win is single instance
- [ ] trim the UI's ~75 MB runtime memory (frontend heap profiling)
- [ ] clipboard / IME (ibus) / fonts / folder picker / title bar theme checked by hand

## Success Criteria
- ~~Window total RSS < 120 MB~~ not reachable with WebKitGTK (floor ~180 MB PSS); target now: no worse than Qt, one window only, no visible lag.

## Risk Assessment
- WebKitGTK version differences across distros; needs `libwebkit2gtk-4.1` installed (document it, or ship AppImage).
- Tauri build is heavy: capped, one at a time.

## Security Considerations
- Restrict webview navigation to the daemon origin; no Tauri IPC commands exposed beyond what is needed.

## Next Steps
- Phase 08.
