# Phase 5 — Docs, AGENTS.md, release

## Context links
- `src/drover/config/config_agents_doc.py` (AGENTS.md written into the config dir)
- `README.md`, `docs/project-changelog.md`
- Herdr app reference: `~/.config/herdr-app/AGENTS.md` (written for people and agents)

## Overview
Priority: medium. Status: planned. Make the new files usable by a person and by an agent asked to
"add a panel" or "move the agents list".

## Requirements
- AGENTS.md: the files (settings/keys/machines/rules JSON, layouts, mods), the layout node reference, the mod
  API with types (`drover.d.ts` written next to it like Herdr's `herdr.d.ts`), permissions, how to check a
  change (errors in Settings), examples.
- README: short section + migration note (TOML → JSON, backups `.toml.migrated`).
- Changelog entry; release tag after the user approves.

## Related code files
Modify: `config_agents_doc.py`, `README.md`, `docs/project-changelog.md`.
Create: generated `drover.d.ts` source in the repo, written to the config dir on start.

## Todo
- [ ] AGENTS.md + drover.d.ts
- [ ] README + migration note
- [ ] full test run (once, announced, capped), frontend build
- [ ] changelog + release (ask first)

## Success criteria
An agent given only AGENTS.md can add a working mod and move a block (try it once, real run).

## Risks
Docs drift from code → d.ts generated from the bridge method table.

## Security
Docs state what mods cannot do (network, token, exec) and how permissions work.
