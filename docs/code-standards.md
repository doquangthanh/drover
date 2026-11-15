# Code standards

General: YAGNI/KISS/DRY, kebab-case file names, files under ~200 lines, real code (no mocks), conventional commits.

## Python (`src/drover`)
- aiohttp daemon; RPC methods register in `rpc/`; every data channel needs the daemon token.
- Tests: `.venv/Scripts/python.exe -m pytest -q`. `tests/daemon_harness.py` boots the real app.

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
