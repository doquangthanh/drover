# Phase 01 spike findings (2026-11-16)

Status: **automated checks GO; manual claude session NOT RUN yet (needs the user's terminal).**

## Verified (ran it)
- pyte 0.8.2 keeps truecolor (`38;2` -> hex `010203`), 256-colour (`48;5;200` -> `ff00d7`), bold/reverse, wide chars (2nd cell is `""`).
- Alt screen: own wrapper swaps main/alt `pyte.Screen` on `?47/?1047/?1049`; `?1049l` restores main text (7 unit tests pass).
- Key mapping (17 tests pass): arrows (normal + app-cursor), ctrl+c, shift+tab, esc, enter, backspace, F-keys, ctrl/shift+arrows, alt+x.
- Textual 8.2.8 headless (Pilot): `a, tab, shift+tab, ctrl+c, escape, up, enter` all reach the widget with `on_key` + `prevent_default`.
  Resize 60x10 -> 100x30 reaches emulator and the debounced size callback.
- **Ctrl+Q is a priority Textual binding and quits the app** (not delivered to the widget). Phase 04 must own quit via the prefix key.
- Bench (isolated daemon, real ws replay, 524,211 chars incl. alt screen): feed **371 ms** (target < 1.5 s); row_runs+style for 200x50 **8.7 ms** (target < 30 ms); process RSS 148 MB (includes the in-process test daemon, so TUI alone is lower).

## Not verified
- Real `claude` session (permission dialog, `/` menus, paste, fullscreen mode, 5 min soak): run `spike_single_pane_app.py` (scratchpad) against a pane.
- Textual draws ANSI named colours with its own palette, not necessarily the terminal's palette (guessed, check by eye).
- Mouse reporting, selection/copy in the pane (not built).
