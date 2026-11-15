# Phase 02: Backend sub-agent events

**Priority:** high · **Status:** todo · depends on phase 01

## Files
- create `src/drover/cli/cli_hook_claude.py` — `drover hook claude <event>`: read stdin JSON, map to
  `{pane, kind, sub_id, name, text}`, fire-and-forget RPC `agent.subagent` (1s timeout, always exit 0).
- modify `src/drover/cli/cli_main.py` — register `hook` command.
- create `src/drover/rpc/methods_subagents.py` — `agent.subagent {pane, event, id, name, text}` →
  `messages.add("sub-start" | "sub-done" | "blocked", ...)` with virtual id `<pane>/<id>`; validate pane.
- modify `src/drover/core/agent_messages_log.py` — `for_tree` also matches virtual ids whose prefix
  is a pane in the tree.
- modify claude launch (where drover builds argv for kind `claude`, see `resolve_argv` /
  `session_manager.create_pane`) — add `--settings` with drover hooks (decision from phase 01).
- modify `src/drover/chat/chat_session.py` — on messages with `parent_tool_use_id`, emit the same
  events for the chat's pseudo-pane (coordinate: file has uncommitted changes from another session).
- tests: `tests/test_cli_hook_claude_payload_mapping.py`, `tests/test_rpc_subagent_events.py`.

## Rules
- Hook never blocks or fails Claude: swallow errors, no output on stdout.
- Truncate texts (200 chars); ignore unknown events.
