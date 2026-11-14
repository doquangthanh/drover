---
title: "Public browser access to herd via cloud relay"
description: "Static UI on Cloudflare Pages, daemon dials out to a Workers+DO relay, OAuth + pairing, E2E-encrypted sessions, public installers."
status: pending
priority: P1
effort: 80h
branch: main
tags: [relay, cloudflare, packaging, security, e2e, web]
created: 2026-11-14
---

# Public browser access via cloud relay

Goal: anyone installs herd, runs `hd cloud link`, signs in at app.herd.dev and drives their agents from any browser.
Daemon stays on the user's machine and only makes OUTBOUND connections. Relay is a blind pipe (E2E encrypted).

## Architecture (one glance)

```
Browser (app.herd.dev, Pages)          Cloudflare Worker (same origin /api/*, /relay/*)        User machine
 UI + E2E (WebCrypto) ──wss /relay/connect?d=ID──► DO "DaemonRoom"(ID) ◄──wss control (outbound)── hd daemon
                                                     │  "open sid" ─────────────────────────────►  dials
                                                     ◄──wss /relay/daemon/data?sid (outbound)──── data socket
                         D1: users, daemons, pairings, browser keys (public only)               WsClientSession (reused)
```

Key decisions
- One data socket per browser session (daemon dials on demand) -> existing `WsClientSession` + JSON protocol reused unchanged; no relay-side multiplexing envelope.
- Same origin: Pages app + Worker routes on app.herd.dev -> first-party HttpOnly session cookie, Origin check on WS.
- E2E mandatory: relay compromise must not equal shell on every user machine. P-256 ECDH (static+ephemeral) + AES-256-GCM; keys pinned at pairing via secret carried in URL fragment (never reaches relay).
- Local mode untouched: daemon-served UI with token keeps working; cloud is opt-in (`hd cloud link`).
- Distribution: Windows = PyInstaller + Inno Setup on GitHub Releases; macOS/Linux = PyPI + `uv tool install herd` (POSIX PTY backend already exists). Frozen mac/linux binaries deferred.

## Phases

| # | Phase | Effort | Status |
|---|-------|--------|--------|
| 1 | [Daemon packaging, installers, CI, update check](phase-01-daemon-packaging-installers-and-ci.md) | 16h | pending |
| 2 | [Relay (Workers+DO+D1), OAuth, pairing, daemon cloud link](phase-02-relay-auth-pairing-and-daemon-cloud-link.md) | 26h | pending |
| 3 | [E2E channel + web UI adaptation + Pages build](phase-03-e2e-channel-and-web-ui-relay-mode.md) | 24h | pending |
| 4 | [Public site, legal, hardening, docs](phase-04-public-site-legal-and-hardening.md) | 14h | pending |
| 5 | [Billing (optional, deferred)](phase-05-optional-billing-note.md) | 0h | cancelled-by-default |

## Dependencies
- P1 independent; can run in parallel with P2.
- P3 needs P2 relay API + daemon cloud link. P4 needs P2+P3 (security review covers both). P5 needs P4.
- External: domain (herd.dev placeholder), Cloudflare account (Workers Paid for DO), Google + GitHub OAuth apps, PyPI project name, optional code-signing cert.

## Biggest risks
1. Relay = remote-shell gateway -> E2E + pinned keys + per-device revoke; external crypto review before launch.
2. Version skew: cloud UI always latest, daemons lag -> protocol version in hello, min-compat banner.
3. DO cost under chatty terminal output -> coalescing window for cloud sessions, per-account bandwidth quota.
4. Abuse of relay as generic tunnel (opaque E2E bytes) -> per-account quotas, connection caps, bans.

## Unresolved questions
See end of each phase file; consolidated list in phase-04.
