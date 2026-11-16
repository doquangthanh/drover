# Phase 01 — Spike: terminal emulation inside Textual (go/no-go gate)

## Context links
- `src/drover/core/pane_session.py` (replay buffer 512K chars, `output_listeners`, pyte flushed every 0.15 s)
- `src/drover/core/pane_screen_text.py` (daemon pyte use: text only, "good enough to read text")
- `src/drover/core/terminal_mode_tracker.py` (comment: "pyte ignores" alt screen / mouse / bracketed paste)
- `src/drover/core/alt_screen_history_reader.py` (Claude fullscreen mode + OpenCode draw on alternate screen)
- `src/drover/daemon/ws_client_session.py` (protocol doc at top), `src/drover/cli/cli_attach_terminal.py`
- textual-terminal: https://github.com/mitosch/textual-terminal ; textual-tty: https://pypi.org/project/textual-tty

## Overview
Priority P1 (blocks all). Status pending. Prove a pane running `claude` renders and types correctly in a Textual widget.

## Key insights — options compared
| Option | Verdict | Evidence |
|---|---|---|
| A. Own widget: pyte `Screen` fed by ws `replay`+`out`, Line API render | **Recommended** | pyte already a dep (pyproject, verified). ws already streams raw bytes + full replay on attach (ws_client_session.py `_attach`, verified). Line API draws only visible rows (Textual docs, not re-read now = guessed detail). |
| B. `textual-terminal` | Reject | README: widget takes `command=` and runs it itself (verified from README); we need to feed bytes from the daemon. Pyte-based anyway, so no gain over A. Maintenance unclear (guessed). |
| C. `textual-tty` (bittty emulator) | Fallback only | PyPI: pure-Python emulator, early versions "buggy and a bit slow" (search result summary, not verified in code). Check if it accepts an external byte stream only if A fails. |
| D. Daemon `pane.screen` via `pane.read` | Reject | Returns plain text only (`pane_read` / `visible_lines`, verified), pyte updated max ~7x/s (verified), no colours/cursor. Colours would need a new daemon RPC = breaks "daemon unchanged". |

Known gaps of pyte (from repo comments, verified): ignores `?1049` alt screen, mouse modes, bracketed paste.
Guessed (spike must check): truecolor `38;2` support in pyte 0.8.2, wide chars/emoji width, `?2026` sync output ignored harmlessly,
speed of feeding a 512K-char replay (pure Python; might take ~1 s).

## Requirements
- Functional: attach one pane, show colours/bold/reverse/cursor, type (letters, Enter, arrows, Ctrl+C, Esc, Tab, Shift+Tab, paste),
  resize widget -> `pane.resize`, survive Claude's redraws and fullscreen (alt screen) mode.
- Non-functional: input echo feels instant (<50 ms extra), redraw capped ~30 fps, attach (replay) < 1.5 s on 512K replay, RSS < 150 MB.

## Architecture
```
ws "replay"/"out" ─> TerminalEmulatorScreen.feed(data)   (pure, no Textual)
                        ├─ splits stream on ?47/?1047/?1049 h/l -> swaps main/alt pyte.Screen
                        ├─ TerminalModes (reuse) for bracketed paste / app-cursor
                        └─ dirty rows set
TerminalPaneView (Widget, Line API)
   render_line(y) -> Strip(segments from pyte row, Rich Style from Char fg/bg/bold/italics/underscore/reverse)
   refresh throttled via set_timer(1/30) when dirty
   on_key -> textual_key_to_bytes() -> conn.send_input(pane, data) ; event.stop(); event.prevent_default()
   on_paste -> wrap in \e[200~ ... \e[201~ when bracketed_paste
   on_resize -> rpc pane.resize(cols, rows) (debounced 150 ms) + emulator.resize
```

## Related code files
Create (kept as real foundation, not throwaway):
- `src/drover/tui/__init__.py`
- `src/drover/tui/terminal_emulator_screen.py` (pyte wrapper + alt screen swap + to-Strip conversion helpers, <150 lines)
- `src/drover/tui/textual_key_to_bytes.py` (Textual `Key` -> bytes; reuses `core/terminal_key_names.KEYS`, adds `\eOA` arrows when app-cursor mode)
- `src/drover/tui/terminal_pane_view.py` (Line API widget)
- `tests/test_tui_terminal_emulator_screen.py`, `tests/test_tui_textual_key_to_bytes.py`
Scratch only (not committed): `<scratchpad>/spike_single_pane_app.py` (tiny App: ensure_daemon -> ws -> one TerminalPaneView), `<scratchpad>/bench_replay_feed.py`.
Modify: `pyproject.toml` (add `textual`), `uv.lock` (via `uv add textual`; ask user before running).

## Implementation steps
1. `uv add textual` (light install; ask first). Record installed version.
2. Write `TerminalEmulatorScreen`: `feed(str)`, `resize(cols, rows)`, `rows_as_segments()`/`line(y)`, `cursor`, `dirty`; alt-screen swap by splitting input on the mode regex.
3. Write key mapping: printable `event.character` passthrough; named keys via `KEYS`; `ctrl+<letter>` via `encode_key`; Alt via `\e` prefix.
4. Write `TerminalPaneView`; disable app/screen bindings that steal keys (Tab focus cycling, Ctrl+Q/Ctrl+C defaults) while focused — verify which ones the installed Textual version binds.
5. Scratch app against real daemon: run `claude` in a pane (`dr run --bg claude`), attach, use it 5 min: prompt, permission dialog, arrows in menus, Esc, Shift+Tab, paste, `/` commands, resize the terminal.
6. Bench: feed a saved 512K replay (`pane.read` is text; capture raw via ws replay to file) into emulator; time it; time one full render of 200x50.
7. Write findings into `plans/261116-0943-textual-tui-client/reports/spike-terminal-emulation-findings.md` (go / no-go + numbers).

## Todo
- [ ] textual installed, version recorded
- [ ] terminal_emulator_screen.py + tests
- [ ] textual_key_to_bytes.py + tests
- [ ] terminal_pane_view.py
- [ ] manual run with claude (normal + fullscreen mode) done
- [ ] replay bench numbers recorded
- [ ] go/no-go written

## Success criteria (how checked)
- Unit: feeding `"\x1b[31mhi"` gives red `h`,`i` cells; `?1049h` then text then `?1049l` restores main screen text — `pytest -q tests/test_tui_terminal_emulator_screen.py`.
- Unit: Key `up` -> `\x1b[A` (and `\x1bOA` in app-cursor mode), `ctrl+c` -> `\x03`, `shift+tab` -> `\x1b[Z` — `pytest -q tests/test_tui_textual_key_to_bytes.py`.
- Manual: claude session usable end-to-end in scratch app; no garbled frame after 5 min (eyeball, note in report).
- Bench: replay feed < 1.5 s, render < 30 ms (numbers in report). If replay too slow: feed in chunks with `await asyncio.sleep(0)` between, or show last N KB first.
- **Gate**: if colours/redraw are badly broken and not fixable in ~2 h, stop and report to user before phase 02 (fallback: try option C, or TUI with "open in `dr attach`" for the focused pane).

## Risks
- pyte misses sequences Claude uses -> garbled UI. Mitigation: manual test list above; patch via small pre-filter in the wrapper.
- Textual swallows keys (Tab, Ctrl+C, Ctrl+Q, Esc delay) -> mitigation: widget-level `on_key` + `prevent_default`, check Textual's ESC delay setting.
- PTY size is single per pane: web UI and TUI fight via `pane.resize` (last writer wins). Accept; document. No daemon change.
- pyte CPU on heavy output -> throttle refresh; measure RSS/CPU with `ps` during the bench.

## Security
Token from `daemon_info_file` (same as `dr attach`), sent as `?token=` on localhost ws only; never logged.

## Next steps
Phase 02 wraps the ws code from the scratch app into `DaemonConnection`.
