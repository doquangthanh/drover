# Phase 02: Windows packaging (dr-py.exe) and direct pane PATH

## Context Links
- `packaging/drover.spec`, `.github/workflows/release-windows.yml`
- `src/drover/self_command.py`, `src/drover/core/windows_cli_runtime_installer.py`

## Overview
Priority P1. Status: todo. Ship the Rust `dr.exe` at the root of `drover-cli-windows-x64.zip`, the Python CLI
beside it as `dr-py.exe`; panes call `dr.exe` directly instead of through `dr.cmd` (cmd.exe costs ~15 ms).

## Key Insights
- Runtime folder layout stays `runtime/<ver>/dr.exe` + `.complete`, so the installer and `dr.cmd` shim keep working.
- Python code that re-launches "dr" from the runtime must target `dr-py.exe` only where it needs Python itself;
  `dr_command()` already returns the owner drover.exe for daemon/window.
- Old zips (no dr-py.exe) still work: Rust dr.exe is only in new zips.

## Requirements
- spec: CLI onedir exe named `dr-py`; CI builds Rust `dr.exe` (`--no-default-features`, MSVC) into the folder.
- Pane PATH: `runtime/<ver>` (when installed) before `shims`, so `dr` resolves to the exe; `hd` stays on the shim.
- `fast_cli_command()` (Claude hooks) keeps pointing to runtime `dr.exe` (Rust handles `hook claude`).

## Related Code Files
- Modify: `packaging/drover.spec`, `.github/workflows/release-windows.yml`, `src/drover/self_command.py`,
  `src/drover/core/windows_cli_runtime_installer.py` (zip check accepts the new layout)

## Implementation Steps
1. spec rename + CI cargo step + smoke test (`dr.exe ls` delegates/works, `dr-py.exe --help`).
2. `pane_path`: prepend runtime dir when `runtime_dr_exe()` exists.
3. Tests for pane_path / zip layout.

## Todo List
- [ ] spec  - [ ] CI  - [ ] pane_path  - [ ] tests

## Success Criteria
Fresh install: panes resolve `dr` to Rust dr.exe; `dr tui`, `dr attach`, `dr run` still work via dr-py.exe.

## Risk Assessment
Panes created before the runtime is installed keep the shim (still correct, just slower).

## Security Considerations
Zip-slip checks unchanged; dr-py.exe validated like dr.exe.

## Next Steps
Phase 03.
