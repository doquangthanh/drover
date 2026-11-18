# Phase 09: Packaging, cutover, remove Python

## Context Links
- `packaging/*`, `pyproject.toml`, `README.md`, `docs/*`, self-update code (phase 05)

## Overview
- Priority: P1. Status: todo. Effort: 14h.
- Ship Rust builds for Linux + Windows, move existing users over through self-update, delete the Python code.

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
- [ ] CI builds
- [ ] Windows pass
- [ ] bridge update tested
- [ ] final measurements
- [ ] Python removed, docs updated

## Success Criteria
- Fresh install and upgrade both work on Linux and Windows; targets in plan.md met.

## Risk Assessment
- Upgrade breaks a running session: updater stops the old daemon only after `session.json` is flushed.

## Security Considerations
- Signed/checksummed artifacts; updater verifies before swap.

## Next Steps
- Roadmap/changelog update; close plan.
