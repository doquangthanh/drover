# Phase 4 — Public site, legal, hardening, docs

## Context Links
- Phase 1 artifacts (Releases, PyPI, install.sh), Phases 2-3 relay + E2E
- No `docs/` folder exists yet (user rules expect docs/system-architecture.md, code-standards.md, project-changelog.md, development-roadmap.md)

## Overview
Priority P1 | Status pending | Effort 14h
Launch-readiness: landing/download page, privacy + terms, abuse controls, security review, account deletion, monitoring, docs.

## Key Insights
- Trust is the product: landing must explain plainly "your machine dials out; relay sees encrypted bytes only; unlink anytime".
- Opaque E2E traffic means abuse can only be policed by volume/metadata -> quotas are the main lever.

## Requirements
Functional
- Landing `herd.dev` (separate Pages project, static HTML/CSS, no framework, no third-party trackers): what/why, screenshots, install per OS (Windows installer link to latest Release, `uv tool install`, install.sh), "Open app" -> app.herd.dev, security model, FAQ, GitHub link.
- `/privacy`, `/terms` pages; link from app sign-in screen and installer.
- Account page: delete account (cascade daemons, devices, sessions; DO closes sockets), export minimal data (JSON of rows).
- Abuse controls: per-account monthly relay bytes quota + per-session bandwidth cap; max daemons/devices/concurrent sessions; admin ban flag (D1) checked on connect; Turnstile on sign-in only if bot sign-ups appear (YAGNI until then).
- Status indicators in app when relay degraded (simple `/api/health`).
Non-functional
- Security headers on both Pages projects; HSTS preload after stable.

## Architecture
```
herd.dev (Pages: site/)            app.herd.dev (Pages: built UI) + Worker routes /api/*, /relay/*
  index, download, privacy, terms     D1: + users.banned, usage(user_id, month, bytes)
                                      DO flushes byte counters to D1 on session close (not per frame)
```

## Related Code Files
Create
- `site/index.html`, `site/privacy.html`, `site/terms.html`, `site/style.css`, `site/_headers`
- `relay/src/account-api.ts` (delete/export), `relay/src/usage-quota.ts`
- `relay/migrations/0002_usage_and_bans.sql`
- `docs/system-architecture.md`, `docs/code-standards.md`, `docs/project-changelog.md`, `docs/development-roadmap.md`, `docs/security-model-and-threat-model.md`
- `SECURITY.md` (vuln disclosure contact)
Modify
- `relay/src/daemon-room-durable-object.ts` (quota enforce, ban check), `relay/src/worker-router.ts`
- `README.md` (install + cloud section)
- `src/herd/web/js/cloud/cloud-shell.js` (account delete, legal links)

## Implementation Steps
1. Threat model doc (assets: user shells; actors: relay operator, network, XSS, stolen laptop, malicious user abusing relay) + mitigations mapping.
2. External/peer review of e2e handshake + relay auth; fix findings before public.
3. Usage quota + ban + caps in DO/Worker; tests.
4. Account delete/export endpoints + UI.
5. Landing site + install instructions synced with Phase 1 outputs; Pages deploy workflow for `site/`.
6. Privacy policy notes (below) + terms; get lightweight legal review if possible.
7. Monitoring: Workers analytics + error alerts (no payloads); weekly D1 backup (Time Travel).
8. Load test: N daemons x M sessions with synthetic output on staging; measure DO cost per active hour; tune coalescing/quotas.
9. Docs set + SECURITY.md; changelog/roadmap entries.

Privacy policy notes (data inventory)
- Stored: OAuth provider + id + email, session hashes, daemon names/public keys/token hashes, device labels/public keys, timestamps, monthly byte counts, IP addresses transiently for rate limiting (not persisted beyond logs retention).
- Not stored/not readable: terminal input/output, file contents, RPC payloads (E2E encrypted, relay forwards only).
- No ads/analytics trackers; subprocessors: Cloudflare, GitHub/Google (sign-in). Deletion on request/self-serve.
Terms notes: acceptable use (no using relay as general proxy/tunnel, no illegal content, no attacking others), no warranty, service may change/quota limits, account termination for abuse, user responsible for what runs on their machine/agents.

## Todo
- [ ] threat model doc
- [ ] external security review + fixes
- [ ] quotas, caps, ban flag
- [ ] account delete/export
- [ ] landing site + deploy
- [ ] privacy + terms pages
- [ ] monitoring + D1 backups
- [ ] load/cost test on staging
- [ ] docs/ set + SECURITY.md + README

## Success Criteria
- Review sign-off with no open high/critical findings.
- New user: landing -> install -> `hd cloud link` -> app works in < 5 min on Windows/mac/Linux.
- Cost per active user-hour known; quotas keep worst case bounded.

## Risk Assessment
- Cost blowout from heavy users -> quotas + alerting on Cloudflare billing.
- Legal exposure (remote shell service) -> clear terms, E2E design limits operator liability, no content access.
- Low trust from devs -> open-source relay code, document self-hosting.

## Security Considerations
- Disclosure policy (SECURITY.md), dependency scanning (Dependabot) for Python + npm.
- Admin actions (ban) only via wrangler/D1 console, no admin web UI (YAGNI, smaller attack surface).
- Secrets only in Cloudflare/GitHub secret stores.

## Next Steps
Public launch; Phase 5 only if demand.

## Consolidated Unresolved Questions
- Domain ownership (herd.dev is placeholder) and product/PyPI name collisions.
- Free-tier limits (daemons, sessions, GB/month)?
- Who performs security review (budget)?
- Open-source the relay? (recommended)
- Jurisdiction/entity for terms and privacy.
