"""AGENTS.md written into the config folder so an agent can change herd for the user."""

CONFIG_AGENTS_MD = """# herd config folder

Everything herd does is configured by plain files here. herd reloads them on save.

| File | What it controls |
|------|------------------|
| settings.toml | theme, prefix key, scrollback, shell, notify rules, orchestration policy, agent commands |
| keys.toml | keyboard shortcuts after the prefix key (`[keys] new_agent = "c"`) |
| machines.toml | remote machines reached over SSH (`[machines.vps-1] target = "deploy@vps-1"`) |
| rules/*.toml | status detection rules per agent; same id as a bundled file overrides it |

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

Test a rule against a live pane: `hd rules test <pane>`.
Agents may also report status themselves with OSC 7501:
`printf '\\e]7501;state=blocked\\e\\\\'`.
"""
