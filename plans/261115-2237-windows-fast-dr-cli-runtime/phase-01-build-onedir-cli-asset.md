# Phase 1: build onedir dr.exe on Windows + release asset

## Context
- `packaging/drover.spec` (Windows branch: onefile `EXE(... a_app.binaries, a_app.datas ...)`)
- `packaging/dr_entry.py` (console entry, already used by Linux)
- `.github/workflows/release-windows.yml`

## Overview
Priority: high. Status: todo. Add a second Windows build output without touching `drover.exe`.

## Requirements
- `dist/drover.exe` unchanged (name, onefile, windowed).
- New `dist/drover-cli/` folder: `dr.exe` (console=True) + `_internal/`. Zipped as `drover-cli-windows-x64.zip`.
- Zip root = folder contents (`dr.exe` at top level) so extraction target is the version folder.
- Exclude GUI-only deps from the CLI analysis to cut size: `webview`, `PyQt6`, `qtpy`, `tkinter`
  (verify each is not imported by `drover.cli.*` paths; `dr` never opens the window).

## Implementation steps
1. In spec Windows branch, after the existing `EXE(...)`:
   ```python
   a_dr = Analysis(["dr_entry.py"], pathex=["../src"], datas=datas, hiddenimports=hidden,
                   excludes=["tkinter", "webview", "PyQt6", "qtpy"])
   exe_dr = EXE(PYZ(a_dr.pure), a_dr.scripts, [], exclude_binaries=True, name="dr", console=True, **ICON)
   COLLECT(exe_dr, a_dr.binaries, a_dr.datas, name="drover-cli")
   ```
   (Reuse `analysis()` helper by adding an `excludes` param — DRY.)
2. Workflow: after build, `Compress-Archive dist/drover-cli/* dist/drover-cli-windows-x64.zip`;
   smoke test `dist/drover-cli/dr.exe --help`; attach both files to the release; upload both as artifacts.
3. Local check: `uv run pyinstaller packaging/drover.spec --noconfirm` then time `dist/drover-cli/dr.exe --help`.

## Todo
- [ ] spec: CLI onedir build on Windows (+ excludes)
- [ ] workflow: zip, smoke test, attach
- [ ] local build + timing sanity check

## Success criteria
`dist/drover-cli/dr.exe ls` works against a running daemon; `drover.exe` still opens window + CLI.

## Risks
- Hidden import missing after excludes -> smoke test `dr --help`, `dr ls`, `dr hook claude < sample.json`.
- Build time ~2x on CI: acceptable.
