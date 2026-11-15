# Phase 03: Frontend virtual lanes

**Priority:** medium · **Status:** todo · depends on phase 02

## Files
- modify `frontend/src/views/agent-flow-logic.ts` — `virtualAgents(messages)`: derive sub-agents from
  `sub-start`/`sub-done` (id, owner pane, name, state working|done); lanes = you, pane, its subs…
  `activityBars` treats virtual ids like panes. Unit tests in `agent-flow-logic.test.ts`.
- modify `frontend/src/views/agent-flow-board.tsx` — lane card for virtual agent (badge "sub", name =
  subagent_type); FLOW_VERB for new kinds (`sub-start` → "delegates", `sub-done` → "returned").
- modify `frontend/src/views/agent-tree-list.tsx` — optional: show running/finished sub-agents as
  non-selectable children of their pane (dim, no actions).
- modify `frontend/src/views/views-logic.ts` — MESSAGE_VERB for new kinds (Messages tab).

## Done when
Typecheck, vitest, build pass; manual run from plan.md "Success" shows sub lanes.
