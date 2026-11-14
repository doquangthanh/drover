# Phase 1 — Daemon packaging, installers, CI, update check

## Context Links
- packaging/herd.spec (PyInstaller onedir: herd.exe window + hd.exe CLI/daemon), packaging/hd_entry.py, herd_entry.py
- pyproject.toml (hatchling, version 0.1.0 hardcoded; also in src/herd/__init__.py)
- src/herd/pty/pty_backend_factory.py (win -> pywinpty ConPTY; else ptyprocess POSIX backend exists)
- src/herd/cli/cli_autostart.py (Windows Startup folder + systemd --user; NO macOS launchd)
- No .github/ yet, no docs/ yet.

## Overview
Priority P1 | Status pending | Effort 16h
Make herd installable by anyone: Windows installer, PyPI package for macOS/Linux, CI test matrix, tagged releases, daily update check.

## Key Insights
- PTY layer is NOT Windows-only: `posix_pty_backend.py` (ptyprocess) exists. Unverified on macOS/Linux in CI -> CI matrix is the real check.
- Audience = devs running coding agents; Python/uv is near-universal there. `uv tool install herd` on mac/linux avoids notarization, universal2 builds and glibc pinning. Frozen mac/linux binaries = YAGNI for now.
- pywebview needs GTK/Qt on Linux at runtime; desktop window must degrade to "open in browser" when backend missing (check `desktop_window_launcher.py` already falls back to webbrowser).
- Version duplicated in two places -> single source via `[tool.hatch.version] path = "src/herd/__init__.py"`.

## Requirements
Functional
- Windows: per-user installer (no admin) `herd-setup-X.Y.Z.exe`; installs to `%LOCALAPPDATA%\Programs\herd`, adds dir to user PATH (`hd`), Start-menu shortcut, optional "start at sign-in" checkbox (calls `hd autostart on`), uninstaller stops daemon (`hd server stop`) and removes autostart; keeps state dir unless user ticks "remove data".
- macOS/Linux: `pipx install herd` / `uv tool install herd`; `install.sh` one-liner (installs uv if absent then `uv tool install herd`).
- macOS autostart via `~/Library/LaunchAgents/dev.herd.daemon.plist`.
- Release on git tag `v*`: GitHub Release with Windows installer + zip + SHA256SUMS; wheel+sdist to PyPI (trusted publishing, no stored token).
- Update check: once/24h, GET `api.github.com/repos/<org>/herd/releases/latest`, cache in state_dir; expose `update` in `server.info` + state; `hd status` prints notice; UI banner. Setting `update_check = false` opts out. Notify only, never auto-install.
Non-functional
- No telemetry. Update check sends only a standard request (no IDs).
- CI < 15 min.

## Architecture
```
tag v0.2.0 ─► release.yml
  ├─ windows-latest: uv sync → pytest → pyinstaller herd.spec → iscc herd-installer.iss → (optional sign) → upload
  ├─ ubuntu-latest: uv build → pypa/gh-action-pypi-publish (OIDC)
  └─ create GitHub Release + SHA256SUMS
push/PR ─► ci.yml: matrix {windows, ubuntu, macos} × py3.12: ruff + pytest
```

## Related Code Files
Create
- `.github/workflows/ci.yml`, `.github/workflows/release.yml`
- `packaging/herd-installer.iss` (Inno Setup 6)
- `packaging/install.sh` (also published on landing site)
- `src/herd/core/update_checker.py` (fetch+cache latest version, compare, <80 lines)
Modify
- `pyproject.toml` (dynamic version, classifiers, urls, optional extra `desktop = [pywebview]` if Linux import pain confirmed)
- `src/herd/cli/cli_autostart.py` (darwin launchd branch)
- `src/herd/daemon/daemon_main.py` (schedule update check in `_housekeeping`)
- `src/herd/rpc/methods_system.py` (`server.info` includes `update`)
- `src/herd/cli/cli_commands_admin.py` (`hd status` notice)
- `src/herd/web/js/*` small banner (reuse toast/conn-banner pattern)
- tests: mark Windows-only tests with `skipif`, add posix PTY smoke test

## Implementation Steps
1. Single-source version (hatch dynamic version). Add `--version` sanity test.
2. Add ci.yml matrix; fix tests that fail on POSIX (paths, shells, `icacls`, ConPTY assumptions). Add a posix PTY spawn/echo test.
3. Verify `uv build` wheel contains `web/**` and `status/rules/*.toml` (hatch includes package data by default; assert in CI by unzipping).
4. macOS launchd autostart branch in `cli_autostart.py`.
5. Inno Setup script: PrivilegesRequired=lowest, DefaultDirName={localappdata}\Programs\herd, Tasks: addtopath, autostart; [UninstallRun] `hd server stop`; AppId fixed GUID for upgrades; close running herd.exe/hd.exe before upgrade (`CloseApplications=yes`).
6. release.yml: build on tag, attach artifacts, PyPI trusted publishing (configure on pypi.org).
7. `update_checker.py`: async aiohttp GET with 5s timeout, ETag, swallow errors; semver compare via tuple parse.
8. Surface update in `server.info`, `hd status`, UI banner (dismissible, links to Releases / install docs).
9. install.sh: detect uv; else `curl -LsSf https://astral.sh/uv/install.sh | sh`; then `uv tool install herd`; print next steps (`hd server run`, `hd cloud link`).
10. Code signing (optional): document SignPath (free for OSS) or Azure Trusted Signing; add a disabled-by-default signing step keyed on secret presence.

## Todo
- [ ] single-source version
- [ ] ci.yml matrix green on win/mac/linux
- [ ] posix PTY smoke test
- [ ] launchd autostart
- [ ] herd-installer.iss + local build verified (install, upgrade, uninstall)
- [ ] release.yml (GitHub Release + PyPI)
- [ ] install.sh
- [ ] update_checker + server.info + hd status + UI banner + opt-out setting
- [ ] signing step (optional, gated)

## Success Criteria
- Fresh Windows VM: download installer, no admin prompt, `hd status` works in new terminal, upgrade over old version keeps sessions.
- Fresh macOS + Ubuntu: `uv tool install herd && hd server run` -> UI opens, shell pane works.
- Tag push produces Release + PyPI upload with no manual steps.

## Risk Assessment
- Unsigned exe -> SmartScreen "unknown publisher" and AV false positives (PyInstaller bootloader). Mitigate: signing later, submit to MS/Defender false-positive portal, offer zip + PyPI alternative.
- POSIX code paths never exercised -> CI matrix exposes; budget fixes.
- pywebview / desktop-notifier native deps on Linux -> lazy import + fallback to browser / no-op notifier.
- Upgrade while daemon runs locks files -> installer stops daemon first; sessions persist via session.json.

## Security Considerations
- PyPI trusted publishing (OIDC), no long-lived tokens. Pin actions by SHA.
- Publish SHA256SUMS; signing optional.
- install.sh served over HTTPS only; keep it short and auditable.
- Update check never executes downloaded content.

## Next Steps
Phase 2 adds `hd cloud` commands that ship through this pipeline.

## Unresolved Questions
- GitHub org/repo name and PyPI name `herd` availability (likely taken -> `herd-agents`?).
- Need macOS frozen .app for non-dev users? (deferred)
- Code-signing budget?
