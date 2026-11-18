# Phase 09: Packaging, cutover (hybrid: Python CLI/TUI stay)

## Context Links
- `packaging/*`, `pyproject.toml`, `README.md`, `docs/*`, self-update code (phase 05)

## Overview
- Priority: P1. Status: Linux done locally (CI not run yet); Windows not started. Effort: 14h.
- Decision 2026-11-18 (user): hybrid. Phases 06 and 08 are dropped; the Python `dr` (CLI + TUI) stays. Python code
  is NOT removed. Linux ships one bundle: Python `dr` + Rust `drover` (Tauri) + Rust `drover-server` (daemon).
  Windows keeps the all-Python `drover.exe` until its Rust build is tested on a real Windows machine.

## Key Insights
- Users today have a PyInstaller bundle in `~/.local/share/drover` or a `uv tool` install. Self-update must replace
  it with the Rust binaries in one step, keeping state dir and autostart entries.

## Requirements
- Release artifacts: Linux x86_64 (`dr`, `drover`, AppImage or tarball), Windows x86_64 (`dr.exe`, `drover.exe`, MSI/NSIS via Tauri).
- CI build (GitHub Actions) so the low-RAM machine does not build Windows locally.
- Last Python release contains an updater that installs the Rust build.
- Windows checks: ConPTY panes, Ctrl+C, resize, exe swap self-update, WebView2 window.
- Remove: `src/drover/`, Python tests that are fully ported, `pyproject.toml`/`uv.lock` (keep conformance tests only if still useful).
- Docs: README install, `docs/system-architecture.md`, `docs/code-standards.md` (Rust section), changelog, roadmap.

## Architecture
```
GitHub release ── dr, drover (Linux) / dr.exe, drover.exe (Windows)
old Python drover ── self-update ──> Rust binaries (state dir untouched)
```

## Related Code Files
- Create: `.github/workflows/rust-release.yml`, `packaging/linux/*`, Tauri bundle config.
- Modify: README, docs/*, self-update.
- Delete: `src/drover/**`, `packaging/drover.spec`, `packaging/*_entry.py`, ported Python tests.

## Implementation Steps
1. CI matrix build + artifacts.
2. Windows test pass on a real Windows machine.
3. Bridge release (Python) that self-updates to Rust; try it on this machine from the current bundle.
4. Measure final numbers vs baseline (daemon, CLI, window, TUI) into `reports/`.
5. Delete Python code; update docs.

## Todo List
- [x] Linux bundle: `drover.spec` builds only `dr` on Linux (no Qt/pywebview); `release-linux.yml` adds the Rust
  binaries, a smoke test (Python `dr server start` -> Rust daemon) and a `.sha256` per tarball
- [x] Python `dr server run` execs `drover-server` in the bundle (`DROVER_ENGINE=python` opts out); `dr app` opens
  the Tauri window, falls back to the browser without WebKitGTK; Tauri starts `drover-server`
- [x] Rust update.apply: download + SHA-256 check + folder swap with rollback + restart keeping port/token
- [x] install.sh: SHA-256 check, `DROVER_ARCHIVE` for local builds, menu entry runs `dr app`
- [x] built and installed locally (PyInstaller + cargo, capped) into temp dirs: daemon engine=rust, 7.6 MB RSS,
  UI 200, `dr --help` 67 ms, `dr app` window loaded the UI (ws client "ui"; screen was locked, so no screenshot),
  second `dr app` focused the first. Bundle 627 MB -> ~101 MB (tarball 40 MB)
- [ ] CI run on GitHub (needs a push/tag: not done)
- [ ] update.apply against a real release (needs a release with .sha256) — not run; swap/checksum unit-tested
- [ ] bridge from the installed 0.1.33: its updater swaps in the new tarball and restarts via `dr server run`,
  which now execs drover-server (same path as the tested `dr server start`); not run end to end
- [ ] Windows: Rust build + test on a real machine
- [x] docs: README, system-architecture, code-standards (Rust), changelog Unreleased

## Success Criteria
- Fresh install and upgrade both work on Linux and Windows; targets in plan.md met.

## Risk Assessment
- Upgrade breaks a running session: updater stops the old daemon only after `session.json` is flushed.

## Security Considerations
- Signed/checksummed artifacts; updater verifies before swap.

## Next Steps
- Roadmap/changelog update; close plan.
