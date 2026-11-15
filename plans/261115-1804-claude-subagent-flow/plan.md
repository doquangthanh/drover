---
title: Claude Code sub-agents on the Agent tree Flow board
status: proposed
created: 2026-11-15
---

# Plan: show Claude Code sub-agents (Task/Agent tool) as lanes on the Flow board

## Context
Flow board (v0.1.16+) only sees drover panes and `dr run/send/wait`. A `claude` pane that delegates to
planner / researcher / tester through its own Task tool shows ONE lane: the sub-agents run inside the same
process and never reach drover. Goal: each sub-agent call = a virtual lane under its pane, with start,
finish (and result summary), so the user can follow the real orchestration flow like the approved design.

## Sources (both already reachable)
1. **Terminal panes** (`claude` CLI): Claude Code hooks inherit `DR_PANE_ID`, so a hook can run
   `drover hook claude` (CLI) → RPC to daemon. Events: PreToolUse/PostToolUse on the sub-agent tool,
   SubagentStop, Notification (needs you), Stop.
2. **Chat panel** (claude_agent_sdk in daemon): messages carry `parent_tool_use_id`
   (`src/drover/chat/transcript_builder.py:119`) → emit the same events in-process. No hook needed.

## Data model (no breaking change)
- Reuse `AgentMessagesLog`; virtual agent id = `<pane_id>/<tool_use_id>`; new kinds `sub-start`,
  `sub-done` (text = subagent_type · description / short result).
- `messages.list` unchanged; frontend `buildLanes` adds virtual lanes after their pane
  (name = subagent_type, kind badge "sub", state from last event).

## Phases
| # | Phase | Status |
|---|-------|--------|
| 1 | [Research hook payloads + install strategy](phase-01-research-claude-hooks.md) | todo |
| 2 | [Backend: hook CLI, RPC, chat emitter](phase-02-backend-subagent-events.md) | todo |
| 3 | [Frontend: virtual lanes + tree children](phase-03-frontend-virtual-lanes.md) | todo |

## Key decisions to confirm
- Hook install: opt-in toggle in Settings that writes drover's hook into `~/.claude/settings.json`
  (user scope) vs. per-pane `--settings` flag when drover launches `claude`. Recommend per-pane flag
  (no edits to the user's global config; only affects panes drover starts).
- Persist events across daemon restarts? Out of scope (separate item B).

## Risks
- Hook payload field names differ across Claude Code versions → phase 1 pins them, parser tolerant.
- Hook latency: hook must exit fast (fire-and-forget RPC, timeout 1s, never block Claude).
- Parallel sub-agents in one turn → several lanes start at once; ids keep them apart.

## Success
Start `claude` in a drover pane, ask it to use 2 sub-agents in parallel → Flow shows pane lane + 2
sub lanes with started/finished arrows and live bars; same for a chat session.
