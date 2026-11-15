# Phase 3: route shims and hooks to the fast dr.exe

## Context
- `src/drover/self_command.py` (`dr_command`, `pane_path`, `_dr_shim_dir`)
- Callers: `claude_subagent_hooks.py:17` (hook cmd), `session_manager.py:91` (pane PATH),
  `daemon_client.py:45` (daemon spawn), `cli_autostart.py:20` (login autostart)

## Overview
Priority: high. Status: todo. Only short-lived CLI calls switch; daemon/autostart keep `drover.exe`.

## Requirements
- New `fast_cli_command() -> list[str]`: `[str(runtime_dr_exe())]` when available, else `dr_command()`.
- Use it in: `_dr_shim_dir()` shim body, `claude_subagent_hooks.hook_command()`.
- Do NOT use it in `daemon_client` / `cli_autostart` (`dr.exe` is a console app -> would flash a console;
  daemon is long-lived anyway).
- Shim/hook files already rewrite only on change. The shim is a file on PATH rewritten in place, so running
  panes get the fast path on their next `dr` call; the hooks file is read at `claude` launch, so only newly
  started `claude` panes use it.
- Version safety: runtime folder is version-keyed and `runtime_dr_exe()` checks `__version__`, so after an
  update the shim falls back to `drover.exe` until the new runtime is installed.

## Implementation steps
1. Add `fast_cli_command()` to `self_command.py` (lazy-import installer module to avoid import cycles).
2. `_dr_shim_dir()`: body = `@"<fast exe>" %*` (quote each part).
3. `hook_command()`: use `fast_cli_command()`.
4. Re-write shim once runtime install finishes: call `_dr_shim_dir()` at end of `ensure_runtime()` success
   (or expose `refresh_shims()`), so running panes switch immediately.
5. Compile + ruff.

## Todo
- [ ] `fast_cli_command()`
- [ ] shim + hook switch
- [ ] refresh shims after install

## Success criteria
`type %LOCALAPPDATA%\drover\shims\dr.cmd` points to `runtime\<ver>\dr.exe`; `dr ls` in a pane works.

## Risks
- Runtime folder deleted by user while shim points at it -> `dr` fails "not recognized". Mitigation: shim
  body falls back: `@if exist "<fast>" ("<fast>" %*) else ("<drover.exe>" %*)` — cheap, robust. Use this.
