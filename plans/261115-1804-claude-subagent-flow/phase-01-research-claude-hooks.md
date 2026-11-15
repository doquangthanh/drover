# Phase 01: Research Claude Code hook payloads and install strategy

**Priority:** high · **Status:** todo · blocks phases 2–3

## Questions to answer (with doc links + a real captured payload)
1. Hook events covering sub-agents: exact names (PreToolUse/PostToolUse matcher for the sub-agent tool:
   "Task" vs "Agent"), `SubagentStop`, `Notification`, `Stop`; stdin JSON fields
   (`session_id`, `tool_use_id`, `tool_input.subagent_type/description/prompt`, `tool_response`).
2. Does SubagentStop identify WHICH sub-agent stopped (agent id / tool_use_id)? If not, pair via
   PostToolUse of the sub-agent tool instead.
3. Do hooks inherit the pane env (`DR_PANE_ID`, `DROVER`)? Verify on Windows + Linux.
4. Can drover pass hooks per launch (`claude --settings <file|json>`) without touching
   `~/.claude/settings.json`? Merge behaviour with user's own hooks.
5. claude_agent_sdk: fields on sub-agent messages (`parent_tool_use_id`), how to get subagent_type
   and the final result for the chat panel.

## Method
- docs-seeker / context7 for Claude Code hooks + Agent SDK docs.
- Capture: tiny hook script that appends stdin to a file; run one prompt that spawns 2 parallel
  sub-agents; save sample payloads to `plans/261115-1804-claude-subagent-flow/research/`.

## Output
`research/researcher-claude-hooks-report.md`: event table, sample payloads, chosen install method,
unresolved questions.
