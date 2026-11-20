# Benchmark: Drover v0.1.45 vs herdr 0.9.5 (Windows)

Date 2026-11-20. Windows 11, isolated scratch servers (separate DROVER_STATE_DIR / herdr `--session bench`), release
binaries (Drover `dr.exe` from drover-windows-x64.zip v0.1.45, herdr standalone 0.9.5). 30 runs per call, median;
cold start x5; pane creation x10 (`powershell.exe -NoExit` both sides). One run of the script, so ±3-5 ms is noise.

| Metric (ms, median) | herdr 0.9.5 | Drover 0.1.45 |
|---|---:|---:|
| server cold start (to first list) | 251 | 257 |
| list panes, empty server | 22.7 | 21.5 |
| list panes, 10 panes | 22.6 | 26.1 |
| read pane | 22.6 | 23.3 |
| send text, no enter | 25.6 | 23.6 |
| create shell pane | 193 | 190 |

| Memory, server process tree (MB) | herdr | Drover |
|---|---:|---:|
| idle | 27 | 21 |
| + 10 PowerShell panes | 844 | 842 |

## Read
- Same speed: every call within a few ms of each other, inside run-to-run noise.
- Idle server: Drover ~6 MB lighter. With panes the shells dominate (~80 MB per PowerShell), both equal.
- 2026-11-19 run had dr 16 ms vs herdr 25 ms; today both ~22 ms: machine load differs between runs, compare
  the two columns of one run, not runs.

Script: scratchpad `bench-drover-0145-vs-herdr.ps1` (not committed).

## Unresolved
- Linux numbers not measured (no Linux machine here); CI runners are too noisy for ms timings.
- Tauri window launch time: needs the user's Drover window closed (single instance). See "Client apps" below.

## Client apps (2026-11-20 07:30)
herdr has no desktop window on Windows: its client is a TUI (`herdr`) inside a terminal. RAM after 5 s, median of 3;
trees count only children created after their parent (Windows reuses PIDs).

| Client | Kind | Launch to window | RAM |
|---|---|---:|---:|
| herdr 0.9.5 | TUI in conhost | not measured (window owned by the terminal) | 15 MB (herdr + conhost) |
| drover-native 0.1.45 | GPUI window | 767 ms | 43 MB |
| drover 0.1.45 (Tauri) | web UI window | not measured (user's window open: single instance) | 114 MB (6 MB exe + 108 MB WebView2 x5), after hours in use |

- The Tauri window's weight is WebView2 (a browser engine); GPUI draws itself: ~2.5x lighter.
- A TUI is lightest, but needs a terminal around it (Windows Terminal itself ~50-100 MB, shared by its tabs).
- `dr tui` not measured: started through conhost it exits at once in the script (runs fine with redirected I/O).
