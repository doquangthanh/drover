# Phase 2: runtime installer module

## Context
- `src/drover/core/self_update.py` (download helpers, `UpdateError`, `REPO`, `TIMEOUT`, rename-swap pattern)
- `src/drover/daemon/daemon_main.py:92` (`self_update.remove_old_exe()` at daemon start = hook point)
- `src/drover/app_paths.py` (`state_dir()` = `%LOCALAPPDATA%\drover`)

## Overview
Priority: high. Status: todo. New module `src/drover/core/windows_cli_runtime_installer.py` (<200 lines).

## Requirements
- `runtime_dir(version) -> Path`: `state_dir()/"runtime"/version`.
- `runtime_dr_exe() -> Path | None`: `runtime_dir(__version__)/"dr.exe"` if it exists **and** marker file
  `.complete` exists (guards against half-extracted folders), else None. Must be cheap (2 stat calls):
  it runs on every `dr_command()`.
- `ensure_runtime() -> None` (blocking, call in a background thread):
  - no-op unless `is_single_exe()` and version looks like a release (`version_tuple` non-empty, not dev).
  - no-op if already installed.
  - download `https://github.com/{REPO}/releases/download/v{version}/drover-cli-windows-x64.zip` to a temp
    file inside `state_dir()/"runtime"` (same volume -> atomic rename).
  - validate: size > `MIN_EXE_BYTES`, `zipfile.is_zipfile`, contains `dr.exe`; reject entries with `..` or
    absolute paths (zip-slip).
  - extract to `runtime/.tmp-<version>-<rand>`, write `.complete`, rename to `runtime/<version>`.
    If target appeared meanwhile (race with another process), delete tmp and return.
  - all errors logged at info level and swallowed: fallback is today's behaviour.
- `remove_stale_runtimes()`: delete `runtime/*` folders != current version, best effort
  (`shutil.rmtree(..., ignore_errors=True)`; a running old dr.exe just keeps its folder until next time).
- Reuse the download function from `self_update.py` (extract a shared `_download(url, dest)` if not already
  shared — DRY).

## Implementation steps
1. Write module with the 4 functions above.
2. `daemon_main.py`: after `remove_old_exe()`, start `threading.Thread(target=_install_cli_runtime, daemon=True)`
   where `_install_cli_runtime` = `remove_stale_runtimes(); ensure_runtime()`.
3. Compile check: `uv run python -m compileall src/drover -q`.

## Todo
- [ ] module + shared download helper
- [ ] daemon start hook (background thread)
- [ ] compile + ruff

## Success criteria
After daemon start on a release build: `%LOCALAPPDATA%\drover\runtime\<ver>\dr.exe` + `.complete` exist.

## Security
- HTTPS GitHub release URL only, fixed repo; zip-slip check; extraction only under `state_dir()`.

## Risks
- Antivirus locks fresh files during rename -> retry once after 1 s, else give up (fallback works).
