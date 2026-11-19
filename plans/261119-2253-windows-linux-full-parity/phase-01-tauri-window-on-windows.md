# Phase 01: Tauri + GPUI windows on Windows

## Context
- `rust/crates/drover-desktop/` (Tauri, 204 lines, already mostly cfg-clean), `drover-desktop-native/` (GPUI)
- Python window being replaced: `src/drover/desktop/desktop_window_launcher.py`, `bundled_rust_window.py:19`

## Overview
Priority P1. Status todo. Same `drover` window binary on Windows (WebView2), feature parity with pywebview window.

## Key insights
- `daemon_link.rs` already handles `.exe` and `CREATE_NO_WINDOW`; `main.rs` has `windows_subsystem`.
- Missing on Windows: dark title bar (`set_dark_title` is gtk only; Windows needs DWM attr 20/19, what Python does),
  `.ico` window/taskbar icon, AppUserModelID (else blank taskbar icon), WebView2 missing -> browser fallback.
- GPUI on Windows: Zed ships Windows, so supported; check build on GNU, else MSVC only.

## Requirements
- `cargo build -p drover-desktop -p drover-desktop-native` on Windows (GNU local, MSVC CI).
- Pick folder, open path, platform, dark title, single instance focus, follow daemon restart: same as Linux.

## Related code files
- Modify: `drover-desktop/src/bridge_commands.rs` (Windows `set_dark_title` via DwmSetWindowAttribute on `hwnd()`),
  `drover-desktop/src/main.rs` (icon, AppUserModelID), `tauri.conf.json` (add `icons/icon.ico`), `build.rs`.
- Modify: `src/drover/desktop/bundled_rust_window.py` (drop the win32 skip; `drover.exe` name per Q3).
- Create: `drover-desktop/icons/icon.ico`.

## Implementation steps
1. Build both crates on Windows, fix compile gaps.
2. Windows dark title through DWM in `set_dark_title`; same JS bridge call.
3. Icon + AppUserModelID; WebView2 absent -> `open_in_system_browser` path already in `main.rs`.
4. Launch `dr app` -> Rust window on Windows via `bundled_rust_window.py`.

## Todo
- [ ] build drover-desktop on Windows
- [ ] build drover-desktop-native on Windows
- [ ] dark title (DWM)
- [ ] icon / taskbar id
- [ ] `dr app` opens Rust window on Windows

## Success criteria
Manual: window opens, theme switch flips title bar, second launch focuses, daemon restart followed, folder picker.

## Risks
- GPUI may need MSVC: then local dev builds only the Tauri window. - WebView2 absent on old Win10: browser fallback.

## Security
`is_daemon_page` navigation guard and `open_path` config-dir check unchanged (same code both OS).

## Next
Phase 02 packages these binaries.
