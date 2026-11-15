"""Printed by `dr skill`: teaches a coding agent running inside drover how to use `dr`."""

AGENT_SKILL = """# Working with other agents through drover (`dr`)

You are running inside drover. Every pane has `DR_PANE_ID` set; `dr` uses it to know who you are.

## Start a helper
    dr run --bg --name tests -- codex "write tests for src/cart/discounts.py"
Prints the new pane id. `--on <machine>` runs it on another machine, `--worktree <task>`
gives it its own git branch + folder, `--cwd <dir>` picks the folder.

## Wait for it
    dr wait tests --state done --timeout 900
States: working, blocked (needs a human or an answer), idle, done, exited.
Exit code 2 = timeout, 3 = no such agent.

## Read what it did
    dr read tests --lines 60

## Talk to it
    dr send tests "also cover expired codes"
If the helper is stuck on a permission prompt, the user decides; your answer is forwarded to them.

## See everything
    dr ls          # all agents and states (add --json for machine-readable output)

## Etiquette
- Give helpers a short, specific task and a name.
- Wait, read, then summarise the result for the user.
- Stop helpers you no longer need: `dr kill tests`.
- Don't spawn more than a few helpers; drover enforces a limit.
"""
