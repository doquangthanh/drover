---
title: "Split the monorepo into drover-core, drover-web, drover-desktop"
description: "Three repos with their history kept. Core is the daemon and CLI; web is the browser UI and its window; desktop is the GPUI window."
status: in-progress (local clones done and checked; no remote repo created, nothing pushed)
priority: P2
branch: main
tags: [repo, split, packaging, ci]
created: 2026-11-20
---

# Split into three repos

## Decisions (user, 2026-11-20)
- **drover-core**: daemon, CLI, proto, TUI (Rust crates `core daemon cli proto tui` + Python `src/drover` except `web/`, `web_dist/`).
- **drover-desktop**: `drover-desktop-native` (GPUI) only.
- **drover-web**: everything else for the browser: `frontend/`, `src/drover/web/` (icons, ace, favicon), Tauri window (`drover-desktop` crate) and
  the pywebview launcher (`src/drover/desktop/`). The user said "desktop = GPUI only", so Tauri and pywebview go here (assumption, confirm).
- History of each part is kept (`git filter-repo`). Web and desktop get core through a release, not through the source tree.

## How they connect (verified by reading)
```
drover-web  ──build──► web-<ver>.tar.gz  (web_dist/ + web/)
                               │ unpack to a folder, or DROVER_WEB_DIR
drover-core (daemon) ◄── serves /ui and /static from that folder (paths.rs web_root(), http.rs; Python: app_paths.py)
        ▲  RPC / WebSocket (drover-proto)
drover-desktop (GPUI) ── Rust dependency on drover-core + drover-proto  ◄── the hard part
```
- Web ↔ core: only the folder contract and the RPC protocol. Easy. Core already answers 503 "UI not built" when the folder is missing.
- Desktop ↔ core: `drover-desktop-native` has `path` dependencies on `drover-core` and `drover-proto` (Cargo.toml). Needs a real
  dependency: git dependency with a tag (fast, no registry) or publish crates (cleaner, more work). Recommend git tag first.
- Shared workspace parts to copy or split: `[patch.crates-io]` (xattr, zed-xim, portable-pty vendored) and `[profile.release]`.
  `vendor/zed-xim` and `vendor/xattr` are only for GPUI → desktop. `vendor/portable-pty` is for core.
- Core keeps `include_str!` of `src/drover/status/rules/*.toml` and `pyproject.toml`: stays inside core, no change.

## Phases
| # | Phase | Status |
|---|---|---|
| 1 | Freeze: tag the monorepo, list every file → repo (path map), check no file belongs to two repos | done: path map applied by git filter-repo (core 149 commits, web 41, desktop 10) |
| 2 | Core: cut `src/drover` (minus web), `rust/crates/{core,daemon,cli,proto,tui}`, tests, scripts; remove web/Tauri from its CI | done: cargo check --workspace and 487 Python tests pass |
| 3 | Web: cut `frontend/`, `src/drover/web`, Tauri crate, pywebview launcher; own CI; release `web-<ver>.tar.gz` | done: npm build + 141 tests pass, Tauri crate cargo check passes (with path deps) |
| 4 | Desktop: cut `drover-desktop-native`, vendor dirs it needs; depend on core by git tag; own CI + release | done: cargo check passes (with path deps); Settings > Server included |
| 5 | Installers: pieces per repo, `assemble-bundle` joins them into the old bundle layout | done locally: script tested with fake pieces + install.sh; CI workflows YAML-valid but NOT run |
| 6 | Docs, README, site/pages, links, and archive or redirect the old monorepo | todo |

## Open questions (need the user)
1. **Where does the installer live** (phase 5)? Recommend core: its release workflow downloads the web archive and the desktop binary.
2. **Repo names and owner**: `doquangthanh/drover-core|web|desktop`? Creating repos and pushing is outward-facing: only after approval.
3. **Old repo** `doquangthanh/drover`: keep as archive, or reuse its name for core (keeps stars, releases, Pages URL)?
4. **Version rule**: one protocol version in `drover-proto`; web and desktop declare which core versions they work with.
5. Windows `drover.exe` is a PyInstaller bundle with pywebview: it needs web + core together. Confirm it stays one bundle.

## Risks
- Cross-repo breaking changes (RPC) are no longer one commit. Mitigation: protocol version check at connect time.
- `filter-repo` rewrites history: do it on fresh clones in the scratchpad, never on this working copy.
- CI minutes and Windows build times triple. Mitigation: web and desktop CI only on their own paths.

## How it will be checked
Each new repo: clean clone → build → its own tests. Then one end-to-end: core daemon + web archive in `DROVER_WEB_DIR` serves `/ui`;
desktop connects to that daemon. Report any step not run as "not run".


## Phase 5 design (done)
- Release order for tag vX: (1) core tag, (2) web and desktop: set their drover-core dependency tag to vX, tag vX (a guard step fails otherwise,
  because the Tauri window installs the bundle of its own VERSION), (3) run core `assemble-bundle` with tag vX.
- Core publishes `drover-core-<os>-<arch>`; web `drover-web-<tag>.tar.gz` + `drover-window-<os>-<arch>`; desktop `drover-native-<os>-<arch>`.
  `scripts/assemble-bundle.sh` checks each SHA-256 and writes `drover-<os>-<arch>.(tar.gz|zip)` (+ `.sha256`, + `drover.exe` on Windows):
  the same layout as before, so `self_update_apply.rs`, `launcher.rs` and `install.sh` keep their logic.
- Updater, install.sh and the Python updater now read releases of `doquangthanh/drover-core`.
- Remote step (needs the user): RENAME the existing repo `drover` to `drover-core` (GitHub redirects old URLs, the updater's curl uses -L),
  so installed copies keep finding updates. Then core gets the d41a... change as a normal commit on top of the real history; web and desktop are new repos.
