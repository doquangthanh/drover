# Role templates (CLI only)

## Context
- Plan: [plan.md](plan.md)

## Overview
- Priority: P2
- Status: done
- `dr run <template> "task"` starts a ready-made role; `dr templates` lists them.

## Key insights
- Templates: `config_dir()/templates/<name>.md`, YAML-like frontmatter (`name`, `description`, `command`) + Markdown body.
- Template wins over a program of the same name only when the file exists; `dr run claude ...` is unchanged.
- argv = shlex.split(command) + [body.strip() + "\n\n" + task] (claude/codex take a first prompt as argv).

## Related code files
- src/drover/cli/agent_templates.py (new)
- src/drover/cli/cli_main.py
- src/drover/cli/cli_commands_agents.py
- tests/test_agent_templates.py (new)

## Implementation steps
1. Parse frontmatter (no YAML dependency: `key: value` lines between `---`).
2. `load_template(name)`, `list_templates()`.
3. cmd_run: if command[0] is a template, rebuild the command string with shlex.join.
4. `dr templates [--json]`.
5. Unit tests.

## Todo
- [x] Parse frontmatter (no YAML dependency: `key: value` lines between `---`).
- [x] `load_template(name)`, `list_templates()`.
- [x] cmd_run: if command[0] is a template, rebuild the command string with shlex.join.
- [x] `dr templates [--json]`.
- [x] Unit tests.

## Success criteria
- Unit tests pass; `dr run --bg r1 reviewer "x"` builds `claude ... '<body>\n\nx'`.

## Risks / security
- Agents typing into other agents: keep the existing permission gate (`gate_agent_input`); notes never answer a permission prompt.
