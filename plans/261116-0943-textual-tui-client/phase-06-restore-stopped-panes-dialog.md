# Phase 06 — Restore dialog for stopped panes (after daemon restart)

## Context links
- `src/drover/core/session_persistence.py` (`load_previous` -> `manager.stopped`; `resume(ids, use_resume_command)`; `discard(ids|None)`)
- `src/drover/rpc/methods_workspace.py` (`session.resume` params `panes?, fresh?`; `session.discard` params `panes?`)
- `frontend/src/overlays/restore-logic.ts` (`unaskedStopped`: ask once per pane per session), `frontend/src/actions/pane-actions.ts` (resume/discard calls)

## Overview
Priority P1 (in the minimum slice). Status pending. Modal listing stopped panes on first state that contains any; resume or discard.

## Key insights (verified from code)
- Stopped entry: `{id, name, kind, command, cwd, space_id, tab_id, parent, resume}`.
- Resume uses `resume` command when present unless `fresh=true`; shells always restart plain.
- Web asks once per pane per session -> mirror: client-side `asked: set[str]`.
- Remote machine stopped panes need `machine` param (web groups by machine). TUI slice: local only; remote ids (with `:`) are listed but skipped with a note (YAGNI until remote UI exists).

## Requirements
- Modal: checkbox list (default all checked) showing name, command, cwd (shortened).
- Buttons/keys: `Enter` Resume selected, `f` Fresh start selected, `d` Discard selected, `Esc` Later (keeps placeholders; `C-a r` on a stopped pane resumes that one).
- After action: modal closes; layout updates via normal `state` event.

## Architecture
```
restore_logic.py (pure): unasked_stopped(stopped, asked) ; local_only(stopped)
RestoreStoppedDialog(ModalScreen[tuple[str, list[str]] | None])  -> ("resume"|"fresh"|"discard", ids)
TuiApp.on_state: if unasked -> push_screen(dialog, callback -> conn.rpc(...))
```

## Related code files
Create:
- `src/drover/tui/restore_logic.py`
- `src/drover/tui/restore_stopped_dialog.py`
- `tests/test_tui_restore_logic.py`, `tests/test_tui_restore_dialog_pilot.py`
Modify:
- `src/drover/tui/tui_app.py` (trigger), `src/drover/tui/tui_actions.py` (`r` on stopped pane -> `session.resume {panes:[id]}`)

## Implementation steps
1. Pure helpers + tests (port of `unaskedStopped`).
2. Dialog with Textual `SelectionList` (built-in) + footer key hints.
3. App trigger + callbacks to `session.resume` / `session.discard`.
4. `C-a r`: stopped -> resume; live -> `pane.restart {resume: true}`.

## Todo
- [ ] restore_logic.py + tests
- [ ] restore_stopped_dialog.py
- [ ] app trigger + actions
- [ ] Pilot test

## Success criteria (how checked)
- `pytest -q tests/test_tui_restore_logic.py`: asked set logic.
- `pytest -q tests/test_tui_restore_dialog_pilot.py`: real daemon via harness with a state file pre-seeded so `load_previous` yields 2 stopped shells
  (or call `persistence.save_now()`, rebuild context from same store); app shows dialog listing both; press `d` with one unchecked ->
  `state.stopped` has 1 left; reopen app -> dialog not shown again in same app instance after Esc.
- Manual: `dr server stop` with agents running, `dr server start`, `dr tui` -> dialog -> resume claude with `--resume`.

## Risks
- Harness may not expose store path easily -> check `build_context` signature in `daemon_main.py` (has uncommitted edits: read only).
- Dialog pops up while user types -> only shown once per pane; Esc dismisses.

## Security
Resume runs the saved command again (same as web). Show the command in the list so the user sees what will run.

## Next steps
Phase 07 packaging + docs.
