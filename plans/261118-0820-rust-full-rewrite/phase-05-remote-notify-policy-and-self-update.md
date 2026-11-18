# Phase 05: Remote, notify, policy, self-update

## Context Links
- `src/drover/remote/*`, `src/drover/notify/*`, `src/drover/core/{orchestration_policy,claude_subagent_hooks,
  agent_messages_log,claude_session_id_probe,self_update,windows_cli_runtime_installer}.py`,
  `src/drover/legacy_herd_migration.py`, matching tests

## Overview
- Priority: P2. Status: todo. Effort: 18h.

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
- [ ] id prefixing + registry
- [ ] SSH link + bootstrap
- [ ] notify + policy
- [ ] hooks / messages / session probe
- [ ] self-update

## Success Criteria
- Remote machine panes show up and work in the UI; notifications fire; tests ported green.

## Risk Assessment
- russh lacks some OpenSSH config features (ProxyJump, agent forwarding): fall back to spawning system `ssh -W`.

## Security Considerations
- Honour known_hosts; never disable host key checks; checksum + HTTPS for updates.

## Next Steps
- Phase 06.
