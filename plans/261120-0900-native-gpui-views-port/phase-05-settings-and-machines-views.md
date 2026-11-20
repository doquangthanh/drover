# Phase 05: Settings + Machines views

## Context Links
- Web: `frontend/src/views/{settings-view.tsx,settings-*.tsx,appearance-panel.tsx,machine-add-form.tsx}`

## Overview
Priority P3 · Status todo · Most form widgets; done last.

## Key Insights
- Settings sections: General, Appearance, Notifications, Agents/Rules, Agent policy, Notes for agents (AGENTS.md), Updates.
- RPCs: `settings.files`, `settings.write`, `fonts.list`, `rules.list`, `rules.test`, `notify.test`,
  `update.check`, `update.apply`, `server.info`, `server.stop`.
- Machines: `state.machines`, `machine.test`, `machine.add {..., install}`, `machine.remove`.

## Requirements
- Settings: left section list, right form; toggles, selects, numbers, text; Save writes via `settings.write`.
  Long text files (AGENTS.md, raw settings.toml) shown read-only with "Edit in browser" (no editor in v1).
- Machines: list with status, add form (name, ssh/command), Test, Add (+ install), Remove with confirm.
- Updates: check + apply with confirm.

## Architecture
```
views/settings/mod.rs, sections.rs, form.rs, updates.rs
views/machines.rs
```

## Related Code Files
- Modify: `views/mod.rs`, `views/widgets/controls.rs` (select, number)
- Create: files above

## Implementation Steps
1. Select + number controls.
2. Settings sections one by one (General, Appearance, Notifications, Policy, Rules, Updates).
3. Machines list + add/test/remove.
4. Build, screenshot vs web `#settings`, `#machines`.

## Todo List
- [ ] controls
- [ ] settings sections
- [ ] machines
- [ ] Build, screenshot

## Success Criteria
- Change a setting natively, web shows the same value after reload; add/remove a test machine (only if the user agrees).

## Risk Assessment
- `settings.write` format must match the web exactly: copy params shape from TS, no guessing.

## Security Considerations
- server.stop, update.apply, machine.remove: confirm. Never log tokens or ssh commands with secrets.

## Next Steps
Phase 06.
