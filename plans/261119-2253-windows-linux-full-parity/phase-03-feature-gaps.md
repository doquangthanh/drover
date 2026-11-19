# Phase 03: Turn on the features that are off on Windows

## Context
- `rust/crates/drover-daemon/src/manager.rs:178` (follow cwd), `status_monitor.rs:113` (claude resume),
  `status_monitor.rs:152` (title fallback), `drover-core/src/foreground_probe.rs` (`running_agent`, `follow_cwd`)

## Overview
Priority P1. Status todo. Remove the three `cfg!(windows)` feature switches; OS code only below one shared fn.

## Key insights
- Claude resume: `~/.claude/sessions/<pid>.json` exists on Windows (checked locally). Use `fg_agent` pid (set by
  `running_agent`) for both OS instead of `foreground_pgid` -> just drop the `cfg!(windows)` guard.
- Follow cwd: Windows needs the cwd of another process: PEB -> RTL_USER_PROCESS_PARAMETERS.CurrentDirectory via
  NtQueryInformationProcess(ProcessBasicInformation) + ReadProcessMemory. Put it in `windows_process_tree.rs`
  as `process_cwd`, behind the same `follow_cwd(agent_pid, shell_pid)`.
- Title fallback: run it on both OS (helps ssh panes on Linux too); probe only undoes kinds it set itself
  (`fg_agent`), so the `cfg!(not(windows))` in `probe_foreground` goes away.

## Requirements
Same behaviour, same tests on both OS; no `cfg!(windows)` left in status_monitor.rs / manager.rs.

## Related code files
- Modify: `status_monitor.rs`, `manager.rs`, `foreground_probe.rs`, `windows_process_tree.rs`.

## Implementation steps
1. Claude resume on `fg_agent` pid; drop guard.
2. Windows `process_cwd` (PEB read, 64-bit only, WOW64 -> None); `follow_cwd` shared; drop guard in manager.
3. Title fallback on both OS; remove the probe's platform branch.
4. Tests: own-process cwd on Windows; title fallback table test on both.

## Todo
- [ ] claude resume both OS
- [ ] Windows process cwd + follow cwd
- [ ] title fallback both OS
- [ ] tests

## Success criteria
`grep "cfg!(windows)" status_monitor.rs manager.rs` = only config-type uses; tests green on Windows + Linux CI.

## Risks
PEB layout reads are unsafe: bounds-check lengths, cap at 32K chars, any error -> None.

## Security
Only PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ on the pane's own child processes.

## Next
Python daemon equivalents only if Q2 keeps it.
