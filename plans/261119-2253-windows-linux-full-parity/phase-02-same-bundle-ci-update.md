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
