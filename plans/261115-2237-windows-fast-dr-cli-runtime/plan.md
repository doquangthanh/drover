---
title: Fast `dr` on Windows (unpacked CLI runtime next to the single drover.exe)
status: done (pending release verification)
created: 2026-11-15
mode: auto (medium)
---

# Plan: make every `dr` call on Windows ~3x faster

## Problem (measured 2026-11-15)
- `dr ls` via shim `%LOCALAPPDATA%\drover\shims\dr.cmd` -> `drover.exe` (PyInstaller **onefile**, 32.5 MB): **~400 ms/call**.
- Python import of the CLI is only ~115 ms. The rest is onefile unpacking 32 MB into `%TEMP%\_MEI*` on
  every call (+ bootloader parent/child process + Defender scanning fresh DLLs).
- Hot callers: agent panes (`dr wait/read/prompt/run` via shim), Claude hooks (`dr hook claude` on every
  SubagentStart/Stop, `claude_subagent_hooks.py`). All go through `self_command.dr_command()` / `_dr_shim_dir()`.

## Approach
Keep `drover.exe` as the only thing users download (landing page + self-update unchanged). Additionally ship
`drover-cli-windows-x64.zip` (PyInstaller **onedir** `dr.exe`, console, no unpacking). The running app/daemon
installs it once into `%LOCALAPPDATA%\drover\runtime\<version>\` in the background; once present, shims and
hooks point there. Missing/failed/offline -> silently keep using `drover.exe` (today's behaviour).

Daemon + window stay on `drover.exe` (long-lived, startup cost irrelevant, no console-window issue).

## Phases
| # | Phase | Status |
|---|-------|--------|
| 1 | [Build onedir dr.exe on Windows + release asset](phase-01-build-onedir-cli-asset.md) | done |
| 2 | [Runtime installer module](phase-02-cli-runtime-installer.md) | done |
| 3 | [Route shims/hooks to fast dr.exe](phase-03-route-dr-command-to-runtime.md) | done |
| 4 | [Tests, benchmark, docs](phase-04-tests-benchmark-docs.md) | done |

## Key dependencies
- Phase 2 needs the asset name from phase 1. Phase 3 needs phase 2's `runtime_dr_exe()`.
- Works only for tagged releases (asset must exist for `__version__`); dev/source runs unaffected.

## Success
- `dr ls` through shim <= 150 ms median (from ~400 ms) on a release build.
- First run without network still works (falls back to drover.exe).
- In-app update to vN+1 -> next start installs runtime vN+1; old runtime folders cleaned when unused.

## Out of scope (YAGNI)
- Lazy-import trimming of the CLI (~115 ms import; revisit only if target missed).
- Linux (already onedir).

## Unresolved questions
- Ok to add a 2nd release asset (`drover-cli-windows-x64.zip`, ~30 MB) per tag?
- Background download on first start acceptable, or should it wait for user opt-in?

## Outcome (2026-11-15)
- Measured on this machine (cmd /c, warm, median of 10, `dr ls`): release drover.exe 389 ms; onedir dr.exe with
  setuptools 402 ms; onedir dr.exe without setuptools **189 ms**. So the real cost was PyInstaller's
  `pyi_rth_setuptools` hook, not onefile unpacking. Spec now excludes setuptools/pkg_resources (helps both builds).
- Locally built onefile drover.exe runs ~3.2 s per start on this machine (the CI-built one: 389 ms), likely
  Defender scanning unknown local builds. Single-file timing after the setuptools exclusion still needs checking
  on a CI build; if it is ~190 ms too, the runtime zip/installer could be removed (YAGNI).
- Review fixes applied: shim exit code (`exit /b %errorlevel%`), version-only shim text (no rewrite under running
  cmd), runtime dr.exe not treated as single exe (daemon/autostart go to drover.exe via `.complete`), rename
  before delete for old runtimes, temp age gate, rename retry, HTTPException in download, CRLF shim bug.
- Known limitation: Claude hooks point straight at runtime dr.exe; a claude pane outliving an upgrade + cleanup
  gets failing (non-fatal) sub-agent hooks until restarted.
