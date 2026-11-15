# Code review: Windows fast `dr` CLI runtime (uncommitted)

Scope: release-windows.yml, drover.spec, claude_subagent_hooks.py, self_update.py, daemon_main.py, self_command.py, new windows_cli_runtime_installer.py (~190 LOC changed/added).
Checks: ruff clean on the changed files; imports OK (no cycles); related tests pass (31 passed, 1 xfailed). Shim behaviour checked by running the cmd.exe snippets in the scratchpad.

Score: 6/10. The structure and the zip-slip check are good. Two real bugs: the shim drops the exit code, and dr.exe wrongly treats itself as the single-file drover.exe.

## Critical

1. **The shim's fast path always exits 0** (self_command.py:67, `@exit /b`). I tested it: with a real exe that returns 7, `cmd /c shim.cmd` returns 0, `||` never fires, and PowerShell `$LASTEXITCODE` is 0. The old one-line shim returned 7. Agents that check `dr wait/run/send` exit codes would see every failure as success. The test (tests/test_windows_cli_runtime_installer.py:193) pins the broken text.
   Fix: `@exit /b %errorlevel%` (tested: returns 7). Add a test that actually runs the shim with `cmd /c` on Windows.

## High

2. **The runtime dr.exe thinks it is the single-file drover.exe** (self_command.py:13-15, 25-26). `is_single_exe()` is just frozen + win32, so it is also true inside `<state>/runtime/<v>/dr.exe`. There `dr_command()` returns the runtime dr.exe. What follows:
   - `dr server restart/start` from a pane (daemon_client.py:45) starts the daemon from runtime/<v>/dr.exe. That daemon then:
     - runs in-app updates via `apply_windows_exe(Path(sys.executable))` (self_update.py:103), which swaps the new **drover.exe into runtime/<v>/dr.exe** and leaves the real drover.exe un-updated;
     - writes a shim that falls back to itself;
     - keeps its own runtime folder locked.
   - `dr server autostart on` (cli_autostart.py:20) and `migrate_autostart` write the runtime path into autostart. `remove_stale_runtimes` deletes that path on the next version, so autostart silently breaks.
   - Fix: tell the two builds apart, e.g. `is_single_exe()` also requires `Path(sys.executable).name.lower() == "drover.exe"`, or onefile detection: `sys._MEIPASS` is outside the exe's folder. Have the runtime dr.exe resolve drover.exe from a path the installer records: write `sys.executable` into `.complete`, or into a `drover-exe.txt` next to it. Use that path in `dr_command()` for daemon start, autostart and update.

## Medium

3. **Rewriting dr.cmd while it runs** (self_command.py:71-88, installer:132-135). cmd.exe re-opens a running batch file and seeks to the old byte offset after each command. The background `refresh_dr_shim()` swaps the 1-line body for the 5-line one while panes are inside long `dr wait` calls. When those return, cmd resumes mid-line in the new text, which can produce a garbage command (exit 9009) or run the dr call a second time.
   Fix: make the shim text depend on the version only, so it never changes when the install finishes:
   `@if not exist "<runtime_dir()>\.complete" goto drover` / `@"<runtime_dir()>\dr.exe" %*` / `@exit /b %errorlevel%` / `:drover` / `@"<exe>" %*`.
   This also drops `refresh_dr_shim`, the race between the thread and pane spawns writing the shim at the same time, and the partial-delete case in item 4, because it checks `.complete` the same way `runtime_dr_exe()` does.
4. **Partial cleanup leaves a "present" dr.exe** (installer:108-120). `rmtree(ignore_errors=True)` on an old version whose dr.exe is still running deletes the unlocked files, including lazily-imported modules and `.complete`, but keeps dr.exe and its loaded DLLs. Two consequences:
   - A running old `dr wait` can crash on its next lazy import.
   - An old shim's `if not exist dr.exe` still passes and runs a broken runtime.

   Fix: before deleting, try renaming the folder (`os.rename(entry, entry.with_name(".trash-..."))`). The rename fails while dr.exe runs, so skip that folder and retry next start. Also, item 3's `.complete` check covers the shim.
5. **The Claude hook has no fallback** (claude_subagent_hooks.py:17). The settings file embeds runtime/<v>/dr.exe directly. If that folder is cleaned after an update while a claude pane started earlier is still alive, or is deleted by hand, every SubagentStart/Stop hook errors. Fine if panes always restart with the daemon; otherwise point the hook at the shim, or accept it and document it.
6. **remove_stale_runtimes deletes other processes' in-progress files** (installer:114-120). It removes every `.tmp-*` and `.download-*` regardless of age. If two daemons overlap (restart, or two users of one profile), one wipes the other's extraction mid-way. That is harmless, since it fails closed and retries next start, but it wastes the 30 MB download. Fix: skip temp entries younger than about 10 minutes.
7. **Defender or another rename race fails the whole install** (installer:76). Defender often holds handles on a freshly extracted exe, so `tmp.rename(target)` can raise PermissionError. If a parallel installer won, it raises FileExistsError, and `ensure_runtime` then returns False even though a runtime is installed. Fix: retry the rename 3x with a short sleep. On FileExistsError, check `runtime_dr_exe()` instead of failing.

## Low

8. self_update.py:31-38: `download()` catches only OSError. `http.client.IncompleteRead`/`HTTPException` (a truncated body) escapes as a non-UpdateError and leaves the partial file. Use `except (OSError, http.client.HTTPException)`. The old code had the same gap.
9. installer:82-105: `ensure_runtime(version)` checks `runtime_dr_exe()`, which ignores `version` and uses `__version__`. Pass the version through.
10. The installer has no uncompressed-size cap and no hash check. The source is the project's own GitHub release over TLS, the same trust as the drover.exe update, so this is acceptable. Optionally sum `ZipInfo.file_size` and refuse anything over about 300 MB.
11. Background download of about 30 MB on every daemon start until it succeeds, with no opt-in (an open question in the plan). Offline it costs a 15 s background timeout, which is acceptable.
12. drover.spec:34: a second full Analysis doubles the Windows build time. It could reuse `a_app` (same datas/hiddenimports, only the script differs): `EXE(PYZ(a_app.pure), analysis_scripts...)`. Optional.
13. dr.cmd is written as UTF-8, but cmd reads it in the OEM code page, so profile paths with non-ASCII characters break. Pre-existing, but there are now two such paths per shim.

## Checked and OK
- Zip-slip: absolute paths, `..` and `:` (drive letters/ADS) are rejected. Python's zipfile also sanitizes, and ZipInfo turns `\` into `/` on Windows, so Compress-Archive backslash names still pass the `"dr.exe" in names` check.
- `Compress-Archive -Path dist/drover-cli/*` puts dr.exe and `_internal/` at the zip root, as the installer expects. Multi-line `path:`/`files:` YAML is valid, and the artifact flattens to the dist/ root.
- Spec: the onefile EXE still bundles a_app.binaries/datas, so it stays standalone. The onedir COLLECT mirrors the Linux branch. The CI `dr.exe --help` smoke test is good.
- Imports: self_command -> installer is lazy; installer -> self_command (top level, no drover imports) and self_update (lazy). No cycle.
- Half-extracted folders are never used: the `.complete` marker is written before the rename.
- The `goto` instead of an `if (...)` block works: arguments with `(z)` pass through the fallback intact.
- Version: the CI stamp from the tag means the URL matches the release; dev/rc versions skip the download.

## Recommended order
1 (`%errorlevel%`) -> 2 (is_single_exe split + recorded drover.exe path) -> 3 (version-stable shim, drop refresh) -> 4/7 (rename-before-delete, rename retry) -> the rest.

## Unresolved questions
- Can a claude pane outlive a daemon restart (persistence restore)? This decides whether item 5 matters.
- Is any in-app update path ever run by a process other than drover.exe? This decides how urgent item 2's update case is.
