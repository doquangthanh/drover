# Phase 05: Remote, notify, policy, self-update

## Context Links
- `src/drover/remote/*`, `src/drover/notify/*`, `src/drover/core/{orchestration_policy,claude_subagent_hooks,
  agent_messages_log,claude_session_id_probe,self_update,windows_cli_runtime_installer}.py`,
  `src/drover/legacy_herd_migration.py`, matching tests

## Overview
- Priority: P2. Status: done except the binary swap of update.apply (needs Rust release assets, phase 09). Effort: 18h.

## Key Insights
- Remote = one daemon links to daemons on other machines over SSH and prefixes ids (`id_prefixing`).
- Self-update today swaps a PyInstaller bundle; in Rust it swaps one binary (simpler).

## Requirements
- Remote: `russh` client, bootstrap (install/start remote `dr` if missing), machine registry (`machines.toml`),
  id prefixing, event forwarding. Mixed versions: Rust local + Python remote must work during the move.
- Notify: `notify-rust` (Linux D-Bus, Windows toast); quiet hours + policy decide.
- Subagent hooks file, agent messages log, session id probe.
- Self-update: download release asset, verify checksum, atomic swap (Windows: rename-then-replace like today).
- Legacy herd migration: keep only if still needed (check usage; drop if obsolete).

## Architecture
```
local daemon ── russh ──> remote dr server (127.0.0.1:port via direct-tcpip) ── prefixed ids ──> UI
```

## Related Code Files
- Create: `rust/crates/drover-daemon/src/{remote/*.rs, notify.rs, policy.rs, subagent_hooks.rs, messages_log.rs,
  self_update.rs}`

## Implementation Steps
1. Port id prefixing + machine registry with their tests.
2. SSH link + bootstrap; test against localhost sshd and one real remote.
3. Notify + policy + quiet hours (`test_policy_and_quiet_hours.py` cases).
4. Hooks/messages/session probe.
5. Self-update with checksum; Windows swap test in phase 09.

## Todo List
Decision (2026-11-18): SSH through the system OpenSSH client instead of russh (the risk fallback above, taken
up front): `~/.ssh/config`, ProxyJump, agent and known_hosts behave as in a terminal, less code, lighter build.
The websocket runs over `ssh -W 127.0.0.1:<port>` stdin/stdout (no local port to pick). Notifications use the OS
tools (notify-send / osascript / PowerShell toast); update.check uses the system `curl` (no TLS stack built in).

- [x] id prefixing + registry (`remote/ids.rs`, `remote/registry.rs`, Python test cases ported)
- [x] SSH link + bootstrap (`remote/ssh.rs`, `remote/link.rs`, `remote/hub.rs`, `methods/machines.rs`); WS and
  `/rpc` routing, mixed-id refusal, `hub:` caller prefix
- [x] checked with a stand-in `ssh` (runs the remote side locally with its own state dir, `-W` via socat): Rust hub +
  Python remote daemon 0.1.5 linked, remote space/pane created, pane.send/read, WS attach replay + output +
  routed rpc, auto-reconnect after the remote daemon stopped, machine.remove stops the link (no socat/ssh left)
- [ ] a real remote host over real ssh (none available here) — not run
- [x] notify: messages + quiet hours (`notify.rs`), fired on unfocused status changes / exits and remote status
  events; `notify.test` sent on Linux. macOS/Windows commands written, not run. Policy was already ported (phase 03)
- [x] hooks / messages / session probe: already ported in phase 03 (`launch.rs`, `messages_log.rs`, `claude_session.rs`)
- [x] skill.text (text read from the Python module at build time, one source)
- [x] update.check (GitHub API, redirect fallback); update.apply refuses like a source install
- [ ] update.apply binary swap + checksum (phase 09, once Rust release assets exist)
- [ ] legacy herd migration: not ported (Python-only one-time migration; the hybrid keeps the Python CLI)

## Success Criteria
- Remote machine panes show up and work in the UI; notifications fire; tests ported green.

## Risk Assessment
- russh lacks some OpenSSH config features (ProxyJump, agent forwarding): fall back to spawning system `ssh -W`.

## Security Considerations
- Honour known_hosts; never disable host key checks; checksum + HTTPS for updates.

## Next Steps
- Phase 06.
