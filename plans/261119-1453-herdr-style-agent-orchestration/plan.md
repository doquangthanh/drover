---
title: "Herdr-style agent orchestration in Drover"
description: "Children report to their parent, dr wait --children, role templates, children stop with their parent; in both daemons (Rust + Python)."
status: done (not committed)
priority: P1
branch: feature/rust-rewrite
tags: [orchestration, daemon, cli, rust, python]
created: 2026-11-19
---

# Herdr-style agent orchestration

## Goal
Bring the four `hc` coordination features the user picked into Drover. Same behaviour in the Rust daemon
(`rust/crates/drover-daemon`, the live one) and the Python daemon (`src/drover`, fallback + Windows). The CLI `dr`
is Python only.

## What already exists (verified in code)
- Parent link: `pane.create` stores `parent = caller` (`DR_PANE_ID`); depth limit 3; `pane.close subtree`.
- `orchestration.kill_children_on_parent_exit` (default false) in both daemons, applied in the exit hook.
- `messages.add_state(child, parent, done|blocked|exited)` already fires at the right moments (Flow board only).
- `pane.prompt` submit routine (paste + Enter under the input lock) in both daemons.

## Phases
| # | Phase | Status |
|---|---|---|
| 1 | [Role templates (CLI only)](phase-01-role-templates.md) | done |
| 2 | [Children stop with their parent](phase-02-children-stop-with-parent.md) | done |
| 3 | [dr wait --children all/any](phase-03-wait-children.md) | done |
| 4 | [Children report to their parent](phase-04-child-reports-to-parent.md) | done |
| 5 | [Docs, skill text, build, conformance](phase-05-docs-build-conformance.md) | done |

## Decisions
- Templates live in `~/.config/drover/templates/<name>.md` (frontmatter `name`, `description`, `command`; body =
  instructions). `dr run <template> "task"` → `command` + one argv `body + task`. No daemon change.
- `kill_children_on_parent_exit` default becomes `true`; `dr run --outlive-parent` opts one child out.
- Notes are typed into the parent only when it is a live agent (kind != shell), not blocked, not inside a `dr wait`
  that already covers that child, and has no unfinished draft (keys typed since the last Enter, < 60 s ago).
  Setting `orchestration.notes = true`.
- `dr send parent "..."` resolves `parent` from the caller and wraps the text as `<dr from="%7 review">…</dr>`.

## Constraints
- Low-RAM machine: cargo builds capped (MemoryMax=3G, `-j2`), pytest one file at a time, one heavy job at a time.
- Protocol stays backward compatible: new RPC `pane.wait_children`, new optional params only.

## Risks
- Typing a note into an agent's input could merge with what the person is typing → draft guard (phase 4).
- A parent running Claude inside a shell pane keeps its pane when Claude exits → children are not stopped then
  (documented limit).
