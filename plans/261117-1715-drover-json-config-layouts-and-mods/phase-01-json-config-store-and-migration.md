# Phase 1 — JSON config store + TOML migration

## Context links
- `src/drover/config/settings_loader.py` (SettingsStore, DEFAULT_SETTINGS, DEFAULT_SETTINGS_TOML)
- `src/drover/remote/machine_registry.py` (machines.toml)
- `src/drover/rpc/methods_system.py` (`settings.files`, `settings.write`, CONFIG_FILES)
- `src/drover/config/config_agents_doc.py` (AGENTS.md text), `frontend/src/views/settings-*.tsx`
- Herdr app reference: `~/.config/herdr-app/settings.json`, `keys.json`

## Overview
Priority: high (everything else reads config). Status: planned.
Swap the storage format from TOML to JSON with the same keys and defaults; migrate existing files once.

## Key insights
- Settings are read through `SettingsStore.get("a.b")` everywhere → format change stays inside the store.
- `settings.write` validates TOML today; it must validate JSON (and the known keys) instead.
- The user's real file (`~/.config/drover/settings.toml`) has custom values (e.g. `max_panes = 0`): migration
  must keep them, never reset to defaults.

## Requirements
Functional: settings.json / keys.json / machines.json read with defaults + hot reload; first start writes
defaults; existing TOML migrated once (backup kept as `<name>.toml.migrated`); Settings page edits JSON;
invalid JSON → error shown, last good settings kept.
Non-functional: no new dependency (stdlib `json`); start-up time unchanged.

## Architecture
```
start ─► migrate_toml_to_json(config_dir)  (only when <x>.toml exists and <x>.json does not)
      ─► SettingsStore(json)  ─ reload_if_changed (mtime) ─► data = deep_merge(DEFAULTS, user)
Settings page ─► settings.write(name, text) ─► json.loads + schema check ─► write file ─► reload
```

## Related code files
Modify: `settings_loader.py`, `machine_registry.py`, `methods_system.py`, `config_agents_doc.py`,
`cli_main.py` (help text), frontend `settings-file-panel.tsx` (JSON mode in editor), tests
`test_settings_loader.py`, machine tests.
Create: `src/drover/config/toml_to_json_migration.py`, `tests/test_toml_to_json_migration.py`.

## Implementation steps
1. Add `migrate_toml_to_json(dir)`: for settings/keys/machines, load TOML, write pretty JSON, rename TOML to
   `.toml.migrated`; log each; skip if JSON exists.
2. SettingsStore reads `settings.json` (json.load), same merge/reload/errors; default file = JSON text.
3. Keys + machines loaders → JSON.
4. `settings.write`: accept `*.json` names, validate with `json.loads`; reject unknown names (same allowlist
   logic, paths without `..`).
5. Settings page: editor language JSON; labels/file names updated.
6. Update AGENTS.md text and CLI help.

## Todo
- [ ] migration helper + tests (custom values kept, backup written, idempotent)
- [ ] SettingsStore on JSON + tests
- [ ] keys / machines on JSON + tests
- [ ] settings.write JSON validation + tests
- [ ] Settings page JSON editing
- [ ] docs text

## Success criteria
All existing settings tests pass on JSON; migrating the user's real settings.toml (copy) keeps every value;
a bad JSON save shows an error and keeps the old settings.

## Risks
- Losing a user's settings in migration → backup + idempotent + test with real-shaped files.
- Comments in TOML are lost in JSON → accepted (Herdr app uses JSON too); AGENTS.md documents each key.

## Security
Same allowlist for writable files; no path traversal; config dir permissions unchanged.

## Next
Phase 2 reuses the migration helper for rules.
