"""Printed by `hd skill`: teaches a coding agent running inside herd how to use `hd`."""

AGENT_SKILL = """# Working with other agents through herd (`hd`)

You are running inside herd. Every pane has `HD_PANE_ID` set; `hd` uses it to know who you are.

## Start a helper
    hd run --bg --name tests -- codex "write tests for src/cart/discounts.py"
Prints the new pane id. `--on <machine>` runs it on another machine, `--worktree <task>`
gives it its own git branch + folder, `--cwd <dir>` picks the folder.

## Wait for it
    hd wait tests --state done --timeout 900
States: working, blocked (needs a human or an answer), idle, done, exited.
Exit code 2 = timeout, 3 = no such agent.

## Read what it did
    hd read tests --lines 60

## Talk to it
    hd send tests "also cover expired codes"
If the helper is stuck on a permission prompt, the user decides; your answer is forwarded to them.

## See everything
    hd ls          # all agents and states (add --json for machine-readable output)

## Etiquette
- Give helpers a short, specific task and a name.
- Wait, read, then summarise the result for the user.
- Stop helpers you no longer need: `hd kill tests`.
- Don't spawn more than a few helpers; herd enforces a limit.
"""
