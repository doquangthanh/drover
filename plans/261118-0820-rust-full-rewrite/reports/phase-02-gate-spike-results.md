# Phase 02 gate: spike results (2026-11-18)

Spike: `rust/crates/drover-core/examples/pane_spike.rs` (portable-pty 0.9.0 + alacritty_terminal =0.26.0), release build,
compared with Drover's `PaneScreen` (pyte) on the same raw PTY captures, 120x40.

## Screen text parity
| Capture | Bytes | Result |
|---|---|---|
| shell: `ls --color`, `git log --graph --color`, Vietnamese/CJK/emoji | 9396 | identical |
| `claude` startup (trust dialog, 24-bit colour, cursor moves) | 1481 | identical |
| `top -d 1` | 17294 | identical |
| `nano` killed by SIGTERM (alt-screen leave) | 839 | differs: **Rust correct** |

nano: after `ESC[?1049l` alacritty shows the restored primary screen; pyte has no alt-screen so it keeps nano's
content. Drover works around this in Python (`terminal_mode_tracker.py`, `alt_screen_history_reader.py`); in Rust that
workaround is not needed, but `pane.read` output for alt-screen apps will change (better) and tests must expect it.

## Memory
| Case | RSS |
|---|---|
| process, no panes | ~2.2 MB |
| 1 idle `sh` pane | +0.36 MB |
| 10 idle `sh` panes | 5.0 MB total (~0.29 MB/pane) |
| 1 pane after 18 MB of output, scrollback 5000 x 120 cols full | ~16.8 MB |
| pyte, same 0.9 MB feed | 73 MB max RSS |

Full scrollback costs ~14 MB/pane (cells ~24 B). Mitigation: the daemon's emulator only serves detection, `pane.read`
and search; xterm.js keeps its own scrollback. Use a smaller daemon-side history (e.g. 1000 lines ≈ 3 MB) and keep the
raw replay ring for the UI.

## Throughput
| Engine | shell capture | top capture |
|---|---|---|
| alacritty_terminal | 107 MB/s | 166 MB/s |
| pyte | 0.5 MB/s | 0.6 MB/s |

~200-300x faster: the 0.15 s batching in `pane_session.py` is not needed.

## Other findings
- portable-pty defaults cwd to `$HOME`: always set `CommandBuilder::cwd`.
- Spike binary 650 KB stripped.
- Claude CLI blocks on its trust dialog in a fresh PTY; golden captures of a working session need a trusted dir.

## Verdict
**GO.** Idle target (<= 15 MB with 10 panes) met by a wide margin; parity identical on 3/4, the 4th is a correctness
improvement. Open: Windows ConPTY not tested yet (phase 09 at the latest); golden set should grow (codex, long claude session).
