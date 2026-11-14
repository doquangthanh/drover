# Phase 3 — E2E channel + web UI relay mode + Pages build

## Context Links
- src/herd/web/js/connection.js (builds `ws://location.host/ws?token=`, fixed 1.5s reconnect, rpc/attach/input API used by whole UI)
- src/herd/web/index.html (all assets under absolute `/static/...`, no inline scripts -> strict CSP feasible)
- src/herd/web/js/editor.js (`ace` basePath `/static/vendor/ace`), file-icons.js (`fetch("/static/icons/...")`)
- Phase 2 pairing spec (keys pinned via secret S)

## Overview
Priority P1 | Status pending | Effort 24h
Encrypt every cloud session end to end between browser and daemon; make the existing UI run from app.herd.dev through the relay with sign-in, machine picker and pair page. Local mode unchanged.

## Key Insights
- Only connection.js knows the transport. Everything else uses `conn.rpc/attach/input/onEvent` -> swap transport underneath, UI code untouched.
- Keeping `/static/` prefix in the Pages build means zero path rewrites (copy `src/herd/web/*` -> `dist/static/`, `index.html` -> `dist/index.html`).
- WebCrypto supports ECDH/ECDSA P-256, HKDF, AES-GCM in all evergreen browsers (secure context = https, fine). Python side: `cryptography`.
- Browser private key generated `extractable:false`, stored in IndexedDB (CryptoKey objects are storable) -> XSS can use but not exfiltrate key; strict CSP matters.
- Version skew: Pages UI is always newest; daemons lag. Need protocol version check.

## Requirements
Functional
- Handshake per data socket (after relay `ready`): mutual auth with pinned static keys + ephemeral keys (forward secrecy). Then all frames binary AES-256-GCM.
- Cloud UI: sign-in page (GitHub/Google), machine picker (online state, rename, revoke), `/pair` page (reads fragment, verifies, confirm), devices list, sign-out.
- Connection: exponential backoff + jitter (both modes), distinct states: connecting / machine offline (4404) / unauthorized (redirect to sign-in) / protocol mismatch.
- Mode selection: build injects `<meta name="herd-mode" content="cloud">`; absent = local.
- Hide local-only actions in cloud mode (`server.stop`, open desktop window, "open in OS file explorer" if any).
Non-functional
- Added latency < 30 ms over raw relay; no change to local mode behavior; 238 existing tests still pass.

## Architecture
Handshake (Noise-KK-like, kept tiny; get external review)
```
B→D  {v:1, device_id, eB}              eB = browser ephemeral P-256 pub
D→B  {v:1, eD}                          daemon looks up device_id in trusted browsers; unknown/revoked → close 4401
both: ikm = ECDH(eB,eD) || ECDH(sB,sD)      (sX = pinned static keys)
      k_b2d, k_d2b = HKDF-SHA256(ikm, salt = SHA256(transcript), info "herd-e2e-v1")
frames: binary [12-byte nonce = 4B dir + 8B counter][AES-GCM ciphertext of the existing JSON message]
first encrypted frame each way = {"t":"e2e-ok"} (key confirmation); counter must strictly increase (replay/reorder → close)
```
Daemon: `E2eWebSocket` wrapper exposing `async for msg` (yields TEXT-like objects of decrypted JSON) and `send_str` (encrypts) -> passed into unchanged `WsClientSession`.
Browser: `RelayTransport` with same surface as today's raw WS (`open/close/message/send`) -> `Connection` takes a transport factory.

```
Connection(rpc, attach, input, events)
   ├─ LocalTransport  : ws(s)://host/ws?token=  (today)
   └─ RelayTransport  : wss://app.herd.dev/relay/connect?d=ID → wait relay ready → handshake → E2E frames
```

## Related Code Files
Create (web, each < 200 lines)
- `src/herd/web/js/transport-local.js` (moved from connection.js)
- `src/herd/web/js/cloud/transport-relay.js` (relay socket + handshake + framing)
- `src/herd/web/js/cloud/e2e-crypto.js` (WebCrypto ECDH/HKDF/AES-GCM, HMAC for pairing)
- `src/herd/web/js/cloud/device-keystore.js` (IndexedDB: browser static key, pinned daemon keys)
- `src/herd/web/js/cloud/cloud-api.js` (fetch `/api/*`, 401 → sign-in)
- `src/herd/web/js/cloud/cloud-shell.js` (sign-in screen, machine picker, devices, sign-out)
- `src/herd/web/js/cloud/pair-page.js`
- `src/herd/web/css/cloud.css`
- `scripts/build_cloud_web.py` (copy web → `dist-web/static`, write cloud index.html with meta + CSP, `_headers`, `_redirects` for `/pair`)
- `src/herd/cloud/e2e_channel.py` (handshake + `E2eWebSocket` wrapper, < 200 lines)
- `tests/test_e2e_channel.py` + `tests/fixtures/e2e_vectors.json` (shared vectors)
- `relay/test/e2e-vectors.test.ts` or `src/herd/web/js/cloud/e2e-crypto.test.mjs` (node WebCrypto runs same vectors → interop proof)
Modify
- `src/herd/web/js/connection.js` (transport factory, backoff+jitter, close-code handling, hello/protocol check)
- `src/herd/web/js/app.js` (cloud mode boot: if no session → cloud-shell; pick machine → connect)
- UI spots for local-only actions (grep `server.stop`, desktop launch)
- `src/herd/cloud/cloud_link.py` (wrap data socket with `E2eWebSocket`; cloud coalescing window)
- `src/herd/cloud/cloud_pairing.py` / `cloud_credentials.py` (static key gen + trusted browser list)
- `.github/workflows/release.yml` or new `deploy-web.yml` (build + `wrangler pages deploy` on tag; relay deploy on `relay/**` change)

## Implementation Steps
1. Write e2e spec as a short doc section + JSON test vectors (fixed keys → expected keys/ciphertexts).
2. Python `e2e_channel.py` with `cryptography`; unit tests against vectors, tamper/replay/reorder tests.
3. JS `e2e-crypto.js`; run same vectors under node (`globalThis.crypto.subtle`) in CI.
4. Refactor connection.js into Connection + LocalTransport; verify local mode manually + existing tests.
5. Backoff+jitter (1s→30s), close code mapping, `hello` protocol check (banner: "Update herd on this machine to vX").
6. RelayTransport + device-keystore; pair-page using Phase 2 API (HMAC verify with S, generate device key, claim).
7. cloud-shell (sign-in, machine list w/ online dots, rename, revoke, devices, sign-out); app.js boot branch; remember last machine.
8. Daemon: wrap data sockets in `E2eWebSocket`; reject unknown device ids; cloud coalescing window (~16 ms) to cut DO message count.
9. build_cloud_web.py + Pages `_headers` (CSP: `default-src 'self'; connect-src 'self'; img-src 'self' data: blob:; worker-src 'self' blob:; style-src 'self' 'unsafe-inline'` (verify xterm/ace need), `frame-ancestors 'none'`, HSTS, Referrer-Policy no-referrer).
10. Deploy workflow (Pages + Worker, staging then prod).
11. End-to-end manual test matrix: desktop Chrome/Firefox/Safari, iOS Safari, Android Chrome; flaky network (DevTools offline), daemon restart, relay deploy mid-session.

## Todo
- [ ] e2e spec + vectors
- [ ] python e2e_channel + tests
- [ ] JS e2e-crypto + node vector test in CI
- [ ] connection.js transport split (local mode regression-free)
- [ ] backoff/jitter + close codes + protocol banner
- [ ] RelayTransport + keystore + pair page
- [ ] cloud-shell + app.js boot branch
- [ ] daemon E2E wrapping + device allow-list + coalescing
- [ ] Pages build script + CSP headers
- [ ] deploy workflow staging/prod
- [ ] cross-browser/mobile manual test pass

## Success Criteria
- Relay frames are opaque binary (verified by logging a DO frame in staging); tampered frame closes session.
- Same UI works locally (token) and at app.herd.dev (relay) with identical features minus local-only actions.
- Revoked device cannot connect even if cookie valid; new device needs `hd cloud link`.

## Risk Assessment
- Home-grown handshake bugs -> keep minimal, test vectors, external review (Phase 4) before public launch; alternatively adopt an audited Noise implementation if review demands.
- Losing browser IndexedDB (clear site data, Safari ITP 7-day eviction for script storage) -> device must re-pair. Mitigate: clear UX "re-link this browser", `navigator.storage.persist()`; document Safari behavior.
- Strict CSP may break ace workers / xterm webgl -> test, relax per-directive only.
- UI/daemon protocol drift -> hello version, keep RPC additive, cloud UI tolerant of missing methods.

## Security Considerations
- Relay compromise yields metadata only (who, when, bytes) — not keystrokes/output, cannot inject input.
- Non-extractable keys; strict CSP + no third-party scripts on app origin (no analytics) to limit XSS.
- Nonce = direction + counter; never reuse keys across sessions (ephemeral per socket).
- Pairing secret in fragment; page strips fragment via `history.replaceState` after reading.
- Daemon trusts only pinned device keys; `hd cloud devices` / web revoke both remove trust (daemon side is authoritative).

## Next Steps
Phase 4: public launch hardening, external review, landing + legal.

## Unresolved Questions
- Acceptable that each browser/phone must be paired from the machine (`hd cloud link`)? Alternative: approve new device from an already-trusted browser (more code).
- Safari storage eviction impact on iOS users acceptable?
- Self-host relay option for privacy-sensitive users (relay is small; could document `wrangler deploy` + `HERD_RELAY_URL`)?
