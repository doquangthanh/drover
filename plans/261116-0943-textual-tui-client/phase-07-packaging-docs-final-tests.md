# Phase 07 — Packaging, docs, final test pass

## Context links
- `pyproject.toml`, `uv.lock`, `packaging/drover.spec` (PyInstaller: `collect_submodules("drover")`, data files list)
- `docs/system-architecture.md`, `docs/project-changelog.md`, `docs/development-roadmap.md`, `docs/code-standards.md`, `README.md`

## Overview
Priority P2. Status pending. Make `dr tui` work in the frozen build, document it, run the full suite once.

## Key insights
- PyInstaller spec collects only `drover` data (`web/**`, `status/rules/*.toml`) — the `.tcss` file must be added, and Textual's own
  data/submodules may need `collect_data_files("textual")` / `collect_submodules("textual")` (guessed; verify by running the frozen `dr tui`).
- Python modules use snake_case (existing repo convention); "kebab-case" rule cannot apply to importable Python files.

## Requirements
- `dr tui` works from source (`uv run dr tui`) and from the packaged `dr` binary.
- Docs: architecture section "TUI client", changelog entry, roadmap item, README usage + key list + known limits (single PTY size shared with web UI, no mouse/scrollback yet).

## Related code files
Modify:
- `packaging/drover.spec` (tcss data + textual hooks if needed)
- `docs/system-architecture.md`, `docs/project-changelog.md`, `docs/development-roadmap.md`, `README.md`
- `docs/code-standards.md` (one line: TUI tests use Textual Pilot + daemon_harness)

## Implementation steps
1. Add `tui/*.tcss` to `datas`; build only if user agrees (heavy: run capped, see resource-limits).
2. Smoke the frozen binary: `dr tui` opens, attaches a pane.
3. Docs updates (delegate to docs-manager if preferred).
4. Final run: each new `tests/test_tui_*.py` one by one, then full `pytest -q` once, capped:
   `systemd-run --user --scope -p MemoryMax=3G -p MemorySwapMax=0 -p CPUQuota=200% nice -n 19 ionice -c3 uv run pytest -q`.
5. `ruff check src/drover/tui tests/test_tui_*.py`.

## Todo
- [ ] spec updated
- [ ] frozen smoke (if build approved)
- [ ] docs updated
- [ ] per-file tests pass, full suite once
- [ ] ruff clean

## Success criteria (how checked)
- All `tests/test_tui_*.py` pass individually; full suite passes once (report which ran; skipped = "not run").
- `ruff check` clean on new files.
- Frozen binary smoke recorded, or marked "not run".
- No changes under `src/drover/daemon/`, `src/drover/core/`, `src/drover/rpc/`, `frontend/` — check `git diff --stat` shows only `tui/`, `cli_main.py`, tests, pyproject/uv.lock, spec, docs.

## Risks
- Bundle size grows (Textual + deps). Acceptable; note in changelog.
- Textual version drift breaks Pilot APIs -> pin a compatible range in pyproject.

## Security
No new network surface; client uses existing token-protected `/ws`.

## Unresolved questions
1. `textual` as a core dependency (works in packaged binary, bigger bundle) or optional extra `drover[tui]`? Plan assumes core.
2. Resize fight with web UI open on the same pane: accept last-writer-wins, or later add a daemon "size owner" (needs daemon change, out of scope now)?
3. Default prefix: reuse the daemon setting (`C-a`, shared with web) — OK, or a TUI-specific key (Herdr/tmux use their own)?
4. Should `dr` with no args ever open the TUI when there is no display (ssh)? Currently opens the desktop window; plan leaves it unchanged.
5. Remote-machine panes (`alias:%3`): show read/write in this slice or hide until a remote UI phase?
6. Windows: Textual works on Windows Terminal, but the spike runs on Linux only — test Windows later or now?
7. Herdr-style detach/reattach of the TUI itself is moot (daemon keeps agents alive; TUI is stateless) — confirm no need for a TUI server.
