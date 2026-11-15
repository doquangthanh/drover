# Phase 4: tests, benchmark, docs

## Context
- Existing: `tests/test_self_update.py`, `tests/test_self_update_windows_exe_swap.py` (patterns for tmp dirs,
  monkeypatching `sys.frozen`/`sys.executable`)

## Overview
Priority: medium. Status: todo.

## Tests (new `tests/test_windows_cli_runtime_installer.py`)
- `runtime_dr_exe()` None when folder missing / `.complete` missing; path when both exist.
- `ensure_runtime()` with a real small zip built in tmp (served via monkeypatched download fn writing the
  file — no network): extracts, writes `.complete`, atomic rename; second call no-op.
- Rejects zip-slip entry (`../evil.txt`) and zip without `dr.exe`; nothing left in `runtime/`.
- Not frozen / not win32 -> no-op.
- `remove_stale_runtimes()` keeps current version, removes others.
- `self_command`: shim body contains fallback `if exist` form; `hook_command()` uses runtime exe when present.
Run: `uv run pytest -q` (all must pass) + `uv run ruff check src tests`.

## Benchmark (manual, release build)
PowerShell, 10 runs each, median:
```powershell
1..10 | % { (Measure-Command { & "$env:LOCALAPPDATA\drover\shims\dr.cmd" ls *> $null }).TotalMilliseconds }
```
Before ~400 ms -> target <= 150 ms. Record numbers in changelog.

## Docs
- `docs/project-changelog.md`: entry (faster `dr` on Windows, new release asset).
- `docs/system-architecture.md`: packaging section — onefile app + onedir CLI runtime.

## Todo
- [ ] tests
- [ ] pytest + ruff green
- [ ] benchmark before/after
- [ ] docs + changelog
- [ ] code-reviewer pass
