# Docs, skill text, build, conformance

## Context
- Plan: [plan.md](plan.md)

## Overview
- Priority: P2
- Status: done
- Update `dr skill`, README CLI reference, config docs, changelog; build Rust; run the new tests against both daemons.

## Key insights
- Skill text is Python only (`src/drover/skill/agent_skill_text.py`).
- Config docs exist twice: config_agents_doc.py and rust config_agents_doc.md.

## Related code files
- src/drover/skill/agent_skill_text.py
- README.md
- docs/project-changelog.md
- src/drover/config/config_agents_doc.py
- rust/crates/drover-daemon/src/config_agents_doc.md

## Implementation steps
1. Docs.
2. cargo build -p drover-cli capped.
3. pytest new file: Python daemon, then DROVER_TEST_DAEMON_BIN=<rust bin>.
4. Report what ran.

## Todo
- [x] Docs.
- [x] cargo build -p drover-cli capped.
- [x] pytest new file: Python daemon, then DROVER_TEST_DAEMON_BIN=<rust bin>.
- [x] Report what ran.

## Success criteria
- Both runs pass; skipped checks reported as not run.

## Risks / security
- Agents typing into other agents: keep the existing permission gate (`gate_agent_input`); notes never answer a permission prompt.
