# Phase 4 — Sandboxed mod runtime + bridge API

## Context links
- Herdr app reference: `~/.config/herdr-app/mods/*/` (mod.json + main.js), `herdr.d.ts` (data + commands),
  `AGENTS.md` §Mods
- Drover RPC registry `src/drover/rpc/*`, event hub `src/drover/core/event_hub.py`, web auth (token in URL)
- Phase 3 `ModHost` slot

## Overview
Priority: high. Status: planned. A mod is a folder in `~/.config/drover/mods/<name>/`; it draws its own panel
inside a sandboxed iframe and reaches Drover only through a small message API.

## Key insights
- Isolation: `<iframe sandbox="allow-scripts">` **without** `allow-same-origin` → opaque origin: no cookies,
  no localStorage, no access to the parent page or its token, cannot call the daemon directly.
- Served by the daemon at `/mods/<name>/…` with a strict CSP (`default-src 'none'; script-src 'self'
  'unsafe-inline'; style-src 'unsafe-inline'`; no connect-src) → no network from a mod.
- The parent page is the only gate: it receives `postMessage` calls, checks the method against the mod's
  granted permissions, calls RPC itself, returns results / forwards events.

## Requirements
Functional: mod.json `{name, title, permissions: [...]}`; main.js gets `drover` object:
`spaces()`, `agents()`, `panes()`, `focused()`, `theme()` (colors as CSS vars), `on(event, fn)`,
`run(command, args)` limited to UI commands (open tab, focus pane, switch space, open view, toast),
`pane.send` only with `"panes:write"` permission (asked once, remembered per mod + version hash);
`state.get/set` per mod (kept by the daemon). Hot reload on file change; errors shown in the block.
One example mod shipped (e.g. "recent agents" or a PR list stub using only allowed data).
Non-functional: a broken or slow mod never blocks the UI (iframe; message timeouts).

## Architecture
```
mods/<name>/main.js ─► daemon GET /mods/<name>/ (CSP, token not needed: content is the user's own files,
                       but listing/serving still requires the session cookie/header of the parent page)
parent page  ── postMessage {id, method, args} ◄──► iframe (main.js + bridge shim)
     └─ checks permissions ─► RPC to daemon ─► reply {id, result|error}; events pushed as {event, data}
```

## Related code files
Create: `frontend/src/mods/mod-host.tsx`, `mod-bridge.ts` (permission check, method table), `mod-bridge.test.ts`;
`src/drover/config/mod_store.py`, routes in `web_server.py` / `web_ui_routes.py`, `rpc/methods_mods.py`,
tests; bundled bridge shim `src/drover/web/mod-shim.js`; example `src/drover/config/default_mods/…`.
Modify: phase 3 block registry (`{mod}` → ModHost), Settings page (list mods, permissions, reload).

## Implementation steps
1. Mod store: discover folders, validate mod.json, hash files, hot reload, `mods.list` RPC.
2. Serving route with CSP; shim injected before main.js.
3. Bridge: method table + permission gate + timeouts; events subscription.
4. ModHost in layout blocks; error/reload UI; first-use permission prompt.
5. Example mod + docs snippet.

## Todo
- [ ] mod store + RPC + tests
- [ ] serving route + CSP + tests (no token reachable, no network)
- [ ] bridge with permission gate + unit tests (denied methods, timeouts)
- [ ] ModHost + permission prompt
- [ ] example mod

## Success criteria
A mod in mods/ shows in a layout block, updates live with agent state, can focus a pane; it cannot read the
token, fetch the network, or call `pane.send` without permission (tests prove each).

## Risks
- Serving mods to the phone/remote clients → same auth as the UI; mods are the user's own files.
- Permission UX fatigue → only one sensitive permission (`panes:write`) in v1.

## Security
Sandbox without same-origin, CSP without connect-src, permission gate in the parent, mod names restricted to
`[a-z0-9-]`, no path traversal in the serving route, size limit per file.

## Next
Phase 5 documents the API for people and agents.
