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
Full-screen agents (OpenCode...) are scrolled for you when you ask for more lines than one screen.

## Give it more work and wait for that turn
    dr prompt tests "also cover expired codes" --wait --timeout 900
Exit code 6 = it is on a permission prompt (nothing was typed: read it first), 7 = it never started working
(read it before retrying so the prompt is not sent twice). `dr send` types raw text without these checks.

## Press keys in its UI
    dr keys tests esc            # also: enter, up, down, tab, shift+tab, ctrl+c
If the helper is stuck on a permission prompt, the user decides; your answer is forwarded to them.

## Wait for a plain process (tests, a server), not an agent
    dr run --bg --name unit -- npm test
    dr wait-output unit "passed|failed" --regex --timeout 600

## Names and layout
    dr rename %7 reviewer                 # any later command can use the name
    dr pane split self --direction down -- codex     # prints JSON with the new pane id

## See everything
    dr ls          # all agents and states (add --json for machine-readable output)

## Etiquette
- Give helpers a short, specific task and a name.
- Wait, read, then summarise the result for the user.
- Stop helpers you no longer need: `dr kill tests`.
- Don't spawn more than a few helpers; drover enforces a limit.
"""
