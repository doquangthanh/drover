# Phase 0: GPUI spike (go / no-go)

## Context
- Plan: [plan.md](plan.md)
- Measurements behind the decision: space switch 4.8-12 s on first open in the Tauri window; not daemon, Claude,
  CPU, RAM or replay size (2026-11-19 session).

## Overview
- Priority: P1, Status: done (GO, 2026-11-19)
- Smallest app that answers: does GPUI build and run well here?

## Requirements
- New crate `rust/crates/drover-desktop-native` (bin `drover-native`), `gpui = "=0.2.2"`.
- Window with two panes side by side; each attaches to a real pane over /ws (read-only: no resize, no input in
  the spike), feeds `alacritty_terminal`, draws the grid with colors and cursor.
- Click switches which pane is shown full size (simulates a space switch).

## Measure
- Cold build time and peak RAM under `systemd-run ... MemoryMax=3G` + `cargo build -j2`.
- Vulkan available? (`vulkaninfo --summary`).
- Frame time while a claude pane streams; time to switch panes; RSS of the app.

## Success criteria
- Builds inside the caps; switch < 50 ms; smooth while streaming; RSS well under the Tauri window (~600 MB).

## Risks
- Build OOM at 3G: retry with `-j1`, else ask the user before raising the cap.
- No Vulkan: GPUI falls back? If not, egui path.

## Next
- Go: phase 1. No-go: write findings, switch the plan to egui.

## Result (2026-11-19, debug build, this machine: Intel AlderLake GT1, X11)
- Build: under 3 min total cold (two runs after a dependency fix), peak RSS ~2.3 GB with MemoryMax=3G, `-j2`.
- Fix needed: gpui -> zed-async-tar -> xattr 0.2.3 uses libc::ENOATTR (gone in libc 0.2.19x): patched copy in
  `rust/vendor/xattr-0.2.3` via `[patch.crates-io]`.
- Link needs `libxkbcommon-x11.so` (package libxkbcommon-x11-dev). Without sudo: symlink in
  `target/native-link` + `LIBRARY_PATH`. CI/packaging must install the -dev package.
- Two live claude panes drawn correctly (colors, box drawing, Vietnamese, cursor). Replay of 234 KB fed in 19 ms.
- Switch (show one pane / show both): 12-40 ms from click to painted frame (8 samples), debug build.
- App RSS 164 MB (debug) vs Tauri window ~150 MB + WebKitWebProcess ~600 MB.
- Not measured: release build numbers, Wayland, frame time while streaming heavily.
