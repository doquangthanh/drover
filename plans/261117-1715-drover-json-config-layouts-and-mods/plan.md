# Drover: JSON config, layouts and sandboxed JS mods (Herdr app style)

Status: **Planned** · Branch: `feat/layouts-and-mods` (from `main` after `feat/unlimited-panes` lands)

## Goal
Replace the TOML config with Herdr-app-style files in `~/.config/drover/`, and let the person (or an agent)
reshape the web UI by editing files, without rebuilding Drover:

```
settings.json   keys.json   machines.json        # was settings.toml / keys.toml / machines.toml
rules/<agent>.json                               # was rules/<agent>.toml
layouts/main.json  (+ any other layouts)         # window structure: rows, columns, blocks, sizes
mods/<name>/mod.json + main.js                   # panels in JS, run sandboxed, talk to Drover via an API
AGENTS.md                                        # how to edit all of the above (for people and agents)
```

## Decisions (from the user, 2026-11-17)
- Config like Herdr app: settings.json + keys.json + layouts + mods. Settings page stays, writes JSON.
- Mods run **isolated**: sandboxed iframe, only a whitelisted bridge API (no token, no raw RPC).
- Detection rules move to **JSON** too (bundled and user), with migration of user TOML.

## Phases
| # | Phase | Status |
|---|-------|--------|
| 1 | [JSON config store + TOML migration](phase-01-json-config-store-and-migration.md) | Planned |
| 2 | [Detection rules in JSON](phase-02-detection-rules-json.md) | Planned |
| 3 | [Layout engine in the web UI](phase-03-layout-engine.md) | Planned |
| 4 | [Sandboxed mod runtime + bridge API](phase-04-sandboxed-mod-runtime.md) | Planned |
| 5 | [Docs, AGENTS.md, release](phase-05-docs-agents-md-release.md) | Planned |

Order: 1 → 2 (independent backend) → 3 → 4 (needs 3's blocks) → 5.

## Key dependencies
- Daemon already hot-reloads config by mtime (`SettingsStore.reload_if_changed`, every 2 s): reuse for JSON,
  layouts and mods; push a `config` event so clients reload layouts/mods live.
- Web UI is React + static mount points in `index.html` (`#sidebar`, `#main`, `#topbar`, `#workspace`,
  `#statusbar`); phase 3 replaces the fixed mounts with a layout tree.
- Phone layout (`mobile.css`, `mobile-nav.tsx`) stays as is in v1; layouts apply to desktop widths only.
- Node 22 for frontend build/tests (installed via nvm, not default).

## Out of scope (v1)
- Mods running shell programs (`exec`) — Herdr allows it; not here unless asked later.
- Rewriting built-in panels (sidebar, tabs, chat, changes...) as mods: they become layout **blocks**; mods are
  for new panels. One small built-in mod ships as the example.
- TUI (`dr`) reading layouts/mods.

## Open questions
1. Keep reading old TOML files for one or two releases after migration, or migrate once and ignore them?
   (Plan assumes: migrate once on start, keep `*.toml.migrated` backups, then read JSON only.)
2. May mods send input to panes (`pane.send`)? Plan assumes **yes, only for panes, with a per-mod
   `permissions` list in mod.json** shown to the person on first load.
