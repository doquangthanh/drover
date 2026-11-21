# drover config folder

Everything drover does is configured by plain files here. drover reloads them on save.

| File | What it controls |
|------|------------------|
| settings.toml | theme, prefix key, scrollback, shell, notify rules, orchestration policy, agent commands |
| keys.toml | keyboard shortcuts after the prefix key (`[keys] new_agent = "c"`) |
| machines.toml | remote machines reached over SSH (`[machines.vps-1] target = "deploy@vps-1"`) |
| rules/*.toml | status detection rules per agent; same id as a bundled file overrides it |
| templates/*.md | roles for `dr run <template> "task"`: frontmatter `name`, `description`, `command`; the body is the instructions |

## Detection rule format (rules/<agent>.toml)

```toml
id = "claude"
aliases = ["claude-code"]
resume = "claude --continue"

[[rules]]
id = "permission"
state = "blocked"          # working | blocked | idle
priority = 900             # higher wins
region = "bottom(15)"      # title | bottom(N) | screen
regex = ['Do you want to (proceed|make this edit)']
```

Test a rule against a live pane: `dr rules test <pane>`. Its `reason` says what decided the state
(`osc7501_report:…`, `rule:<id>`, or `no_rule_matched:fallback_…`, which is never `blocked`), and `rule_source`,
`rule_path`, `overrides_bundled` show which file the rules came from.
A one-line status for the sidebar (display only, never changes the state; `:` separates fields, so keep it out of the
text; an empty value clears it): `printf '\e]7501;state=working:summary=indexing docs\e\\'` or just
`printf '\e]7501;summary=indexing docs\e\\'`.
An agent started through a wrapper (`npx`, a sandbox, a script) is not recognised by its program name; name it with
`DROVER_AGENT`: `DROVER_AGENT=claude fence -- claude` (PowerShell: `$env:DROVER_AGENT='claude'; fence -- claude`).
Agents may also report status themselves with OSC 7501:
`printf '\e]7501;state=blocked\e\\'`.
