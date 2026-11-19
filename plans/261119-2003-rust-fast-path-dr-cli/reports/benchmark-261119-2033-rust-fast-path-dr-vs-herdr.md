# Benchmark: Rust fast-path dr vs Python dr vs herdr (Windows)

Date 2026-11-19. Windows 11, isolated scratch servers (separate DROVER_STATE_DIR / herdr session `bench`), one
shell pane each, 30 runs per cell, median ms. Exe called directly (no `dr.cmd`).

| Call | herdr 0.9.5 | dr Rust (this change) | dr Python 0.1.38 |
|---|---:|---:|---:|
| list panes (`pane list` / `ls --json`) | 25.2 | **16.4** | 173.3 |
| read pane | 25.3 | **18.4** | 168.9 |
| send text, no enter | 24.6 | **15.7** | 158.9 |
| `--help` (delegated to Python for dr) | 24.0 | 169.0 | 153.2 |

- Hot commands ~10x faster than Python, ~35% faster than herdr.
- Delegated commands pay ~16 ms extra (Rust start + spawn of dr-py.exe).
- Pane PATH now resolves `dr` to the exe directly; `dr.cmd` adds ~12-20 ms (cmd.exe) when used.
- Parity: `tests/test_rust_fast_dr_cli_parity.py` byte-identical stdout/stderr/exit on all covered forms.
  Found + fixed one real diff: serde_json default float parser off by 1 ulp (`created_at`) -> `float_roundtrip`.

Script: scratchpad `bench-rust-dr-vs-python-dr-vs-herdr.ps1` (not committed).

## Unresolved
- Rust `server` feature build not checked on this machine (GNU toolchain lacks dlltool for windows-sys); Linux CI builds it.
- Windows release CI (MSVC) not run yet; needs a tag/workflow_dispatch.
