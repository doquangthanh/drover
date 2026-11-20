# Phase 3 — Layout engine in the web UI

## Context links
- `frontend/index.html` (fixed mounts `#sidebar`, `#main`, `#topbar`, `#workspace`, `#altview`, `#statusbar`)
- `frontend/src/app.tsx` (portals into those mounts), `frontend/src/shell/*`, `frontend/src/workspace/*`
- `frontend/src/styles/sidebar.css`, `mobile.css`
- Herdr app reference: `~/.config/herdr-app/layouts/main.json`, `AGENTS.md` §Layouts, §Pane frames

## Overview
Priority: high. Status: planned. A JSON tree decides what goes where; today's look is the default layout.

## Key insights
- Herdr's layout model: nodes `row` / `column` / `block` / `stack`, `size` (`px` or `weight`), `min`/`max`,
  `hidden`, `padding`, `gap`, `background` (theme names), block `content` = a built-in or `{ "mod": name }`.
  Pane frames on the tab block: `gap`, `radius`, `border`, `focus`, `header`, `lone`.
- Drover's built-in pieces become named blocks: `brand`, `spaces`, `agents`, `sidebar-footer`, `tabs`,
  `workspace` (pane frames), `status`, `files`, `changes`, `inbox`, `chat`.
- Phone stays on the current fixed mobile UI in v1 (layouts apply at desktop width).

## Requirements
Functional: `layouts/main.json` (default written on first start = current look); `settings.json` `layout`
picks the active one; edit → window updates within ~1 s without reload; invalid layout → error toast and
last good layout kept; unknown block names shown as a labelled placeholder.
Non-functional: no flicker of terminals on relayout (xterm instances keep their DOM; move, don't recreate).

## Architecture
```
daemon: layouts/*.json ─ mtime watch ─► event "layout" {name, tree, errors}
web UI: LayoutRoot(tree) ─► <Row|Column|Stack|Block> (CSS flex, sizes) ─► BLOCKS[name] React component
                                                              └► { mod: name } → ModHost (phase 4)
```
Validation (daemon side): node types, ids unique, sizes, depth ≤ 16, theme color names or #hex.

## Related code files
Modify: `index.html` (single `#app` root), `app.tsx`, shell components (no fixed mount lookup), styles.
Create: `frontend/src/layout/layout-types.ts`, `layout-root.tsx`, `block-registry.ts`, `layout-validate.ts`
(+ tests); backend `src/drover/config/layout_store.py`, RPC `layout.get`, event `layout`, tests.

## Implementation steps
1. Define the JSON schema (types + validator, shared rules in TS and Python).
2. Default `main.json` reproducing today's desktop UI exactly (screenshot compare before/after).
3. LayoutRoot renders the tree; blocks registry maps names → existing components.
4. Daemon layout store + hot reload + `layout` event; frontend subscribes.
5. Pane frame options (`radius`, `gap`, `border`, `focus`, `header`, `lone`) applied to the workspace block.
6. Keep phone path unchanged; switch at the existing mobile breakpoint.

## Todo
- [ ] schema + validators (TS, Python) + tests
- [ ] default layout = current UI (visual check in Qt WebEngine)
- [ ] LayoutRoot + block registry
- [ ] layout store, RPC, event, hot reload
- [ ] pane frame options
- [ ] phone unaffected (check at 390 px)

## Success criteria
Default layout looks the same as today; moving `agents` to the right in main.json moves it live; a broken file
shows an error and keeps the window usable.

## Risks
- Terminals re-mounting on relayout (lost scroll/WebGL) → keep TermEntry DOM nodes, re-parent only.
- Large refactor of `app.tsx` portals → do it behind the default layout first, compare screenshots.

## Security
Layouts are data only (no code); validated server-side before reaching clients.

## Next
Phase 4 fills `{ "mod": name }` blocks.
