# Phase 2 — Relay (Workers + Durable Objects + D1), OAuth, pairing, daemon cloud link

## Context Links
- src/herd/daemon/ws_client_session.py (whole client protocol over one JSON WS: rpc/res, ev, in, attach/detach, out/replay)
- src/herd/daemon/web_server.py (`/ws?token=` local auth), src/herd/daemon/daemon_main.py (`serve`, `_housekeeping`)
- src/herd/remote/remote_link.py (existing outbound aiohttp `ws_connect` + reconnect loop pattern to copy)
- Cloudflare: DO WebSocket Hibernation API (max 32 MiB received msg, 32,768 sockets/DO), Workers Rate Limiting binding, D1.

## Overview
Priority P1 | Status pending | Effort 26h
Build the relay and the daemon's outbound link. After this phase a signed-in browser can open a raw (not yet E2E) WS to its own daemon in a dev environment. E2E + UI in Phase 3; relay must not go public before Phase 3.

## Key Insights
- Protocol is already a single multiplexed JSON stream per client. If the daemon opens one outbound data socket per browser session, `WsClientSession(ctx, ws, label)` works as-is: aiohttp `ClientWebSocketResponse` supports `async for` and `send_str` like the server-side `WebSocketResponse`. -> Relay needs no envelope/session-id multiplexing; DO just splices two sockets.
- Local daemon token stays for local clients; cloud sessions are authenticated by relay (account) + E2E (device keys, Phase 3).
- Daemon max_msg_size is 4 MiB; DO receive limit 32 MiB -> no chunking needed.

## Requirements
Functional
- OAuth sign-in (GitHub, Google) on app.herd.dev -> session cookie.
- Pairing: daemon-initiated, URL-fragment secret (spec below). Max N daemons per user (default 10).
- Daemon control socket: outbound, auto-reconnect (exp backoff 1s..60s + jitter), heartbeat 25s.
- Browser connects to a daemon it owns; relay asks daemon to dial a data socket; splice; close both on either close.
- Machine list API with online/offline + last_seen; rename; revoke daemon; revoke browser device.
- `hd cloud link | unlink | status`; setting `cloud.enabled`, `cloud.relay_url` (env `HERD_RELAY_URL` for dev).
Non-functional
- Relay stores no terminal content, logs no frame payloads; only metadata (ids, timestamps, byte counters).
- Offline daemon -> browser gets close code 4404 quickly.

## Architecture
Components (all in `relay/`, TypeScript, wrangler):
- Worker router: `/api/auth/*` (OAuth start/callback/logout), `/api/me`, `/api/daemons*`, `/api/pair/*`, `/relay/connect`, `/relay/daemon/control`, `/relay/daemon/data`. Static UI served by Pages on same hostname (Worker routes only `/api/*`, `/relay/*`).
- DO `DaemonRoom` (id = daemon_id): holds control socket (tag `ctl`), pending browser sockets (tag `b:<sid>`), daemon data sockets (tag `d:<sid>`). Hibernation API; `serializeAttachment` stores sid/role so routing survives eviction. Forward: `webSocketMessage(ws,msg)` -> peer by tag -> `peer.send(msg)`. Byte counters per sid; caps enforced here.
- D1 tables: `users(id, provider, provider_uid, email, created_at)`, `sessions(id_hash, user_id, expires_at)`, `daemons(id, user_id, name, token_hash, pubkey, created_at, last_seen, revoked)`, `devices(id, user_id, daemon_id, pubkey, label, created_at, revoked)`, `pairings(id, poll_token_hash, daemon_pubkey, daemon_mac, name, user_id?, browser_pubkey?, browser_mac?, expires_at, state)`.

Session flow
```
browser ─wss /relay/connect?d=ID (cookie, Origin=app.herd.dev)─► Worker: session ok? owns ID? not revoked? ─► DO(ID)
DO: control socket present? no → close 4404. yes → sid=rand; accept browser(tag b:sid); ctl.send({"t":"open","sid"})
daemon: dials /relay/daemon/data?sid (Bearer daemon_token) ─► DO accepts (tag d:sid) → send {"t":"relay","ready":true} to browser
then raw frames spliced both ways (Phase 3: binary E2E frames). 10s join timeout → close browser 4408.
```

Pairing (daemon-initiated, relay never sees secret S)
```
hd cloud link: gen daemon static keypair (P-256) if absent; S = 16 random bytes
  POST /api/pair/init {name, daemon_pubkey, mac=HMAC(S, "d"||daemon_pubkey)} → {pair_id, poll_token}  (IP rate-limited, TTL 10 min)
  print + open https://app.herd.dev/pair#<pair_id>.<b64url(S)>   (fragment never sent to server); also print QR-less short form
browser (signed in): GET /api/pair/<id> → verify mac with S → show "Link machine <name>?" → user confirms
  POST /api/pair/<id>/claim {browser_pubkey, mac=HMAC(S,"b"||browser_pubkey), label} → relay creates daemons + devices rows, binds user
daemon long-polls GET /api/pair/<id>?poll_token → {daemon_id, daemon_token (once), browser_pubkey, mac} → verify mac → pin browser key
Second browser (phone): `hd cloud link` again on a linked daemon = "add device" (init authenticated with daemon_token, same flow).
```

## Related Code Files
Create (relay, TypeScript; each file < 200 lines)
- `relay/wrangler.toml`, `relay/package.json`, `relay/tsconfig.json`
- `relay/src/worker-router.ts`, `relay/src/oauth-github-google.ts`, `relay/src/session-cookie.ts`
- `relay/src/pairing-api.ts`, `relay/src/daemons-api.ts`, `relay/src/rate-limits.ts`
- `relay/src/daemon-room-durable-object.ts`
- `relay/migrations/0001_init.sql`
- `relay/test/*.test.ts` (vitest + @cloudflare/vitest-pool-workers)
Create (daemon, Python snake_case per repo convention)
- `src/herd/cloud/__init__.py`
- `src/herd/cloud/cloud_credentials.py` (state_dir/cloud.json owner-only: relay_url, daemon_id, daemon_token, key paths, trusted browser pubkeys)
- `src/herd/cloud/cloud_link.py` (control socket loop; on `open` spawn data socket task -> `WsClientSession(ctx, ws, "cloud")`)
- `src/herd/cloud/cloud_pairing.py` (init, open browser, long-poll, store)
- `src/herd/cli/cli_commands_cloud.py` (`hd cloud link|unlink|status`)
- `tests/test_cloud_link_with_fake_relay.py` (aiohttp test server playing relay)
Modify
- `src/herd/daemon/daemon_main.py` (start CloudLink task if credentials + enabled; stop on shutdown)
- `src/herd/daemon/daemon_context.py` (`cloud: Any = None` for status)
- `src/herd/daemon/ws_client_session.py` (type hint ws as duck-typed; send `hello` event with `protocol` + `version` first)
- `src/herd/rpc/methods_system.py` (`server.info` -> cloud status: linked, connected, sessions)
- `src/herd/cli/cli_main.py` (register `cloud` subcommand)
- `pyproject.toml` (+ `cryptography` dep, used here for P-256 keys and in Phase 3)

## Implementation Steps
1. `relay/` scaffold, D1 migration, wrangler envs (dev/prod), secrets (OAuth client secrets, cookie key).
2. OAuth: GitHub + Google authorization-code + PKCE + `state` cookie; upsert user; session id random 32B, store hash, cookie `__Host-herd_s` HttpOnly Secure SameSite=Lax, 30-day sliding.
3. Pairing API per spec; poll_token and daemon_token stored as SHA-256 hashes; pair rows single-use, TTL 10 min.
4. Daemons API: list (online = DO reports control socket; cache last_seen in D1 on connect/disconnect only), rename, revoke (sets revoked + DO closes sockets), devices list/revoke.
5. `DaemonRoom` DO: control accept (Bearer token check in Worker, pass daemon_id), browser accept, `open` signaling, join timeout via alarm, splice, close propagation, per-sid byte counters, caps (max 10 concurrent browser sessions/daemon, frame <= 4 MiB).
6. Rate limits: Workers Rate Limiting binding on `/api/pair/init` (per IP), `/api/auth/*` (per IP), `/relay/connect` (per user).
7. Daemon `cloud_link.py`: copy reconnect pattern from `remote_link.py`; control messages: `open{sid}`, `revoked` (wipe creds), `ping`. Data socket per sid; on close session cleanup already handled by `WsClientSession.run` finally.
8. `hd cloud link/unlink/status`; `unlink` calls DELETE /api/daemons/self then wipes cloud.json.
9. Tests: relay unit tests (pairing happy path, expired, replay, wrong owner, offline 4404, revoke); daemon test with fake relay (aiohttp server) checking rpc round trip over data socket.

## Todo
- [ ] relay scaffold + D1 schema + wrangler envs
- [ ] OAuth GitHub + Google + session cookie
- [ ] pairing API (init/get/claim/poll) + tests
- [ ] daemons/devices API + revoke
- [ ] DaemonRoom DO splice + timeouts + caps + tests
- [ ] rate limiting bindings
- [ ] daemon cloud_credentials + cloud_link + cloud_pairing
- [ ] `hd cloud` CLI + server.info cloud status
- [ ] hello event with protocol version
- [ ] fake-relay daemon test; full suite still green

## Success Criteria
- `wrangler dev` + local daemon: `hd cloud link` -> browser confirm -> machine shows online; raw WS round-trips `server.info`.
- Daemon offline -> browser 4404 within 1s; daemon restart -> control socket back within backoff window.
- Revoking daemon kills live sessions and daemon wipes credentials.

## Risk Assessment
- DO billing on chatty output (each WS message billed ~1/20 request) -> daemon-side coalescing window (e.g. 16 ms) for cloud sessions only; measure.
- DO eviction/hibernation edge cases losing socket routing -> attachments + tests; daemon reconnect is idempotent.
- OAuth email collisions across providers -> key users by (provider, provider_uid); no auto-merge (YAGNI).
- Cloudflare platform limits change -> keep frame cap configurable.

## Security Considerations
- Relay never sees pairing secret S (URL fragment) -> cannot forge daemon/browser keys. Until Phase 3 E2E lands, relay is dev-only.
- Tokens: 32B random, stored hashed; daemon_token only in owner-only cloud.json (`restrict_to_owner`).
- WS upgrade: validate Origin == app origin (CSWSH), cookie session, ownership, revocation, on every connect.
- No payload logging; Workers logs limited to metadata.
- Pairing endpoints rate-limited; pair ids 10+ chars random, single-use, 10-min TTL.
- Cloud is opt-in; `hd cloud unlink` is a full kill switch; web "Revoke" too.

## Next Steps
Phase 3 wraps the data socket in E2E and adapts the UI.

## Unresolved Questions
- Relay hostname: same origin app.herd.dev (chosen) vs separate relay.herd.dev?
- Max daemons/sessions per free user?
- Should cloud sessions be allowed to call `server.stop` / `settings.write`? (proposal: hide stop in cloud UI, allow settings)
