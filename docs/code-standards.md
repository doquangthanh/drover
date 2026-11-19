# Code standards

General: YAGNI/KISS/DRY, kebab-case file names, files under ~200 lines, real code (no mocks), conventional commits.

## Python (`src/drover`)
- aiohttp daemon; RPC methods register in `rpc/`; every data channel needs the daemon token.
- Tests: `.venv/Scripts/python.exe -m pytest -q`. `tests/daemon_harness.py` boots the real app.

## Rust (`rust/`)
- Cargo workspace: `drover-core` (panes, detection), `drover-daemon` (server, RPC in `methods/`, chat, remote),
  `drover-cli` (bin `dr` = release `drover-server`), `drover-desktop` (Tauri window). Edition 2024.
- The wire protocol is the contract: keep `/ws`, `/rpc`, state files byte-compatible with the Python daemon; the
  Python suite runs against the binary with `DROVER_TEST_DAEMON_BIN`.
- Prefer system tools over heavy crates where the OS has them (`ssh`, `curl`, `notify-send`, `tar`).
- Every cargo run goes through `scripts/cargo-capped.sh` (memory cap); one heavy build at a time.

## Frontend (`frontend/`)
- TypeScript strict; run `npm --prefix frontend run typecheck`, `test` (Vitest, pure logic only) and `build` before pushing.
- State lives in the Zustand store (`core/store.ts`); never mutate it from components, call `actions/` or `connection.rpc`.
- Select narrowly (`useStore(s => s.paneById.get(id))`); wrap list rows in `React.memo`; derive in `core/store-derive.ts`.
- Keep side-effect singletons (connection, terminal registry, keys, editor registry) outside React as plain modules.
- Terminal bytes go straight to xterm; do not route them through React state.
- CSS is global plain CSS in `src/styles/`; reuse existing class names, add rules to the matching file, no CSS-in-JS.
- Shared runtime assets (`/static/icons`, `/static/vendor/ace`) are fetched at runtime, not imported.
- One component per file; one `FileIcon` (`files/file-icon.tsx`) is the only file-icon renderer.
- Layout tree nodes come from the daemon as `{pane}` or `{split: "row"|"col", ratio, a, b}` (`core/protocol-types.ts`).

## Windows and Linux: one app
- One release folder on every OS: `dr` (Rust CLI + daemon), `dr-py` (Python CLI), `drover` (Tauri window),
  `drover-native` (GPUI preview). Same build steps in `release-linux.yml` and `release-windows.yml`.
- A feature is written once. OS code only as a small shim below one shared function (`running_agent`,
  `process_cwd`, `self_update_apply::swap`, PTY/ConPTY): never a feature switched off with `cfg!(windows)` or
  `sys.platform`. Allowed differences: OS APIs and config values (paths, `.exe`, PATH separator, fonts).
- `ci.yml` builds the whole Rust workspace and runs its tests on Linux and Windows for every push: keep it green.
