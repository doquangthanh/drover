# Phase 02: Pane core: PTY, terminal emulation, status detection (GATE)

## Context Links
- `src/drover/pty/*`, `src/drover/core/pane_session.py`, `pane_screen_text.py`, `terminal_mode_tracker.py`,
  `alt_screen_history_reader.py`, `foreground_process_probe.py`, `src/drover/status/*` (OSC 7501, detection rules)

## Overview
- Priority: P1. Status: done. Effort: 24h. **Go/no-go gate** for the whole plan.

## Key Insights
- Python batches pyte updates (0.15 s) because pyte is slow; in Rust the emulator can run on every chunk.
- Detection rules (bundled, Herdr-derived) and OSC 7501 parsing decide agent state: must match Python output exactly.

## Requirements
- PTY: `portable-pty` (Linux openpty, Windows ConPTY); spawn, resize, write, read, kill, exit code.
- Emulator: `alacritty_terminal` (pinned) for screen text, alt-screen, cursor, modes (bracketed paste, app cursor keys).
- Replay buffer (raw bytes ring, same size as Python) for `replay` messages.
- Status: OSC 7501 parser, detection rules engine, status change tracker, foreground process probe (`/proc` on Linux,
  Toolhelp on Windows).
- Workspace models + split layout tree with the same JSON shape (`{pane}` / `{split, ratio, a, b}`).

## Architecture
```
PTY reader task ─bytes─> ReplayRing ──> subscribers (ws "out")
                    └──> Term (alacritty_terminal) ──> screen text / modes ──> StatusTracker ──> events
```

## Related Code Files
- Create: `rust/crates/drover-core/src/{pty.rs, pane_session.rs, screen.rs, modes.rs, replay_ring.rs,
  osc7501.rs, detection_rules.rs, status_tracker.rs, foreground_probe.rs, workspace_models.rs, layout_tree.rs}`
- Reuse as data: bundled detection rule files (read the same files, do not fork them).

## Implementation Steps
1. Spike (4h): spawn `claude` in a PTY under Rust, feed alacritty_terminal, dump screen text; compare with pyte dump.
2. Measure RSS with 10 idle panes and with one pane printing 50 MB. **Gate: <= 15 MB idle + ~1 MB/pane, screen text
   identical on the golden set.** If it fails, stop and re-decide (Go, or keep Python for detection).
3. Port modules one by one with unit tests copied from `tests/test_osc7501_parser.py`, `test_status_change_tracker.py`,
   `test_split_layout_tree.py`, `test_pane_screen_text.py`, `test_foreground_agent_detection.py`,
   `test_detection_rules_bundled.py`, `test_terminal_keys_modes_and_page_merge.py`.
4. Golden files: record raw PTY output of claude/codex/shell sessions once, assert Rust and Python produce the same
   screen text and state sequence.

## Todo List
- [x] spike + gate measurement: [reports/phase-02-gate-spike-results.md](reports/phase-02-gate-spike-results.md) — GO
- [x] pty (Linux tests with real PTY; `cargo check --target x86_64-pc-windows-gnu` clean, ConPTY not run)
- [x] emulator + modes (`screen.rs`, modes from alacritty, no regex tracker) + alt-screen page helpers (`alt_screen_pages.rs`); the async scroll loop moves to phase 03 with the pane RPCs
- [x] OSC 7501 + detection rules (bundled TOML via include_str!) + tracker + foreground probe + key names
- [x] layout tree + workspace models (JSON shape checked against Python)
- [x] golden-file screen parity (`tests/golden/`: shell, claude, nano); state-sequence parity runs in phase 03 via the conformance suite (needs the status monitor loop)

## Success Criteria
- Gate numbers met; all ported unit tests green; golden parity 100%.

## Risk Assessment
- alacritty_terminal breaking changes: pin, wrap behind `screen.rs`.
- ConPTY quirks (resize, Ctrl+C): test on Windows in phase 09 at the latest; keep code behind a trait.

## Security Considerations
- Spawned commands come only from RPC callers holding the token; no shell interpolation of names.

## Next Steps
- Phase 03 builds the server on this crate.
