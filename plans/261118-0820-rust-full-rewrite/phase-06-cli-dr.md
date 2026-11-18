# Phase 06: CLI `dr`

## Context Links
- `src/drover/cli/*`, `src/drover/daemon/daemon_client.py`, `src/drover/skill/*`, `tests/test_cli_parser_and_skill.py`

## Overview
- Priority: P1. Status: todo. Effort: 12h.
- One Rust binary `dr`: all current subcommands, flags, output and exit codes; `server run` and `tui` built in.

## Key Insights
- Agents and scripts call `dr` (and old alias `hd`) heavily: output text and exit codes are an API.
- Current `dr --help` costs 0.03 s / 15 MB; target < 10 ms / < 5 MB.

## Requirements
- clap derive; subcommands: run, ls, send, read, prompt, keys, wait, wait-output, rename, attach, layout cmds,
  server {start,stop,restart,run,ensure,logs,autostart,url}, skill, completion, self update, tui.
- Daemon client: read `daemon.json`, autostart daemon, HTTP `/rpc` (`ureq`, blocking, small), `--json` output.
- `dr attach`: raw terminal over `/ws`.
- `hd` alias kept (second binary name or symlink).

## Architecture
```
dr <cmd> ─ parse (clap) ─ daemon_client (daemon.json, ensure) ─ POST /rpc ─ print / exit code
```

## Related Code Files
- Create: `rust/crates/drover-cli/src/{main.rs, commands/*.rs, daemon_client.rs, attach.rs, completion.rs, autostart.rs}`

## Implementation Steps
1. Snapshot test: run every Python `dr` command with `--help` and typical args, save stdout/exit code as golden files.
2. Implement commands to match the goldens.
3. Autostart (systemd user unit / Windows startup script) with the same file content.
4. Measure startup time and RSS.

## Todo List
- [ ] golden CLI snapshots
- [ ] all subcommands
- [ ] attach
- [ ] autostart + completion
- [ ] timing measured

## Success Criteria
- Golden snapshots identical; `test_cli_parser_and_skill.py` intent covered; `dr --help` < 10 ms.

## Risk Assessment
- Small wording drift breaks agent scripts: goldens are the guard.

## Security Considerations
- Token read from `daemon.json` with user-only file permissions (0600).

## Next Steps
- Phase 07.
