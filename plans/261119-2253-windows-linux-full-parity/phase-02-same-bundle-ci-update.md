# Phase 02: Same bundle, CI and self-update on both

## Context
- `.github/workflows/release-linux.yml`, `release-windows.yml`, `packaging/drover.spec`
- `src/drover/core/windows_cli_runtime_installer.py`, `src/drover/cli/rust_daemon_handoff.py`
- `rust/crates/drover-daemon/src/self_update.rs`, `self_update_apply.rs` (Linux), `self_update_windows.rs`

## Overview
Priority P1. Status todo. One bundle layout (see plan.md), one CI build command, one self-update path.

## Key insights
- Linux: folder bundle, Rust `self_update_apply` swaps it (`cfg!(target_os = "linux")` gates at :18, :42).
- Windows: onefile PyInstaller + runtime zip unpacked by the Python daemon; Rust update shells out to `drover.exe`.
  Onefile is the root of the `_PYI_*` env bugs fixed in 0.1.41: a folder bundle removes that class of bug.
- Make `self_update_apply` OS-neutral: Windows can't overwrite a running exe -> rename old to `.old`, then move new
  in (standard trick), delete `.old` on next start.

## Design (2026-11-19, from reading spec + workflows)
Today the two bundles use the names the other way round:
| file | Linux today | Windows today | Both, target |
|---|---|---|---|
| `dr` | Python CLI | Rust fast CLI + daemon (`dr.exe`) | **Rust** fast CLI + daemon |
| `dr-py` | - | Python CLI (`dr-py.exe`) | **Python** CLI (templates, attach, tui) |
| `drover-server` | Rust daemon | - | symlink/copy of `dr` one release (Tauri `daemon_link` looks for it first), then drop |
| `drover` | Tauri window | Python onefile (window+CLI+daemon) | **Tauri** window |
| `drover-native` | GPUI preview | - | GPUI preview |
| `hd` | symlink -> dr | `shims/` | old name -> `dr` |
- `drover-cli/src/python_fallback.rs` already finds `dr-py` next to itself on unix (exec) and Windows: Linux gets
  the Windows fast path (~16 ms agent calls instead of Python) for free.
- PyInstaller spec: one branch for both OS: onedir `dist/drover/` with `dr-py[.exe]`; Windows onefile goes away
  once `drover.exe` (Tauri) does the first-run install (decision 1). Keep Windows `pywebview` out like Linux Qt.
- Runtime folder `<state>/runtime/<ver>/` (Windows) is replaced by the app folder; `.complete` owner fallback in
  `python_fallback.rs` can go with it.

## Order (each step releasable on its own)
1. Linux: `dr` = Rust, `dr-py` = Python (spec name + assemble step); `drover-server` kept as copy. Smoke test both.
2. Windows: same onedir + Tauri `drover.exe` + `drover-native.exe` in `drover-windows-x64.zip`; keep the old
   onefile `drover.exe` asset one more release for users on 0.1.4x.
3. `drover.exe` (Tauri) first-run install + shortcut/autostart repoint; self-update via shared `self_update_apply`.
4. One matrix workflow; delete runtime installer, `self_update_windows.rs`, Python daemon handoff.

## Requirements
- Both workflows: same steps, same `cargo build -p drover-cli -p drover-desktop -p drover-desktop-native`,
  PyInstaller onedir (`dr-py`) on both, artifact `drover-<os>-<arch>.{tar.gz|zip}` + `.sha256`.
- Ideally one workflow with an OS matrix (ubuntu x64, ubuntu arm64, windows x64) instead of two files.
- Migration: 0.1.4x Windows (onefile) self-updates into the folder layout once; old `drover.exe` path keeps working
  (shortcut/autostart repointed).

## Related code files
- Modify: workflows (merge into `release.yml` matrix), `packaging/drover.spec` (onedir on Windows),
  `self_update_apply.rs` (Windows rename-swap), `self_update.rs` (drop the windows split),
  `rust_daemon_handoff.py`, `windows_cli_runtime_installer.py` (delete once layout is shared), `scripts/install.ps1`
  (create: Windows twin of `install.sh`).
- Delete: `self_update_windows.rs` (after migration release), runtime-unpack code.

## Implementation steps
1. Onedir PyInstaller on Windows; bundle folder same names as Linux.
2. One matrix workflow; smoke test identical on all three runners.
3. OS-neutral `self_update_apply` with rename-swap on Windows.
4. Migration path from onefile (Q1 decides launcher vs zip vs `install.ps1`).
5. Python daemon fallback per Q2.

## Todo
- [ ] onedir Windows bundle
- [ ] matrix release workflow
- [ ] shared self-update apply
- [ ] onefile -> folder migration
- [ ] remove runtime installer + `self_update_windows.rs`

## Success criteria
Tag build gives 3 artifacts from one workflow; Windows update 0.1.4x -> new works hands-off; agents keep running.

## Risks
- Breaking existing Windows installs: ship migration in its own release, keep old path one release.
- Antivirus on fresh exes in user dir: same as today's runtime dir.

## Security
Keep SHA-256 check of downloads on both; no elevation needed (per-user install dir).

## Next
Phase 04 gates parity in CI.
