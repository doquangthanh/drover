# Phase 5 — Billing (optional, out of scope)

## Overview
Priority P3 | Status cancelled-by-default | Effort 0h now (est. 10h if activated)
Only start if relay cost or demand justifies it. Everything else ships free with quotas.

## Key Insights
- Phase 4 quotas already provide the hook: a `plan` column on users mapping to limits (daemons, sessions, GB/month).
- Payment provider (Stripe or Paddle/Lemon Squeezy as merchant of record for VAT) handles cards; herd stores only customer id + plan.

## Sketch (if activated)
- D1: `users.plan`, `users.billing_customer_id`.
- Worker: checkout session endpoint, webhook endpoint (signature verified) -> update plan.
- App: "Upgrade" link on quota-exceeded message; billing portal link.
- Terms/privacy updated with payment processor as subprocessor.

## Risks
- Tax/VAT handling -> prefer merchant-of-record provider.
- Paywall vs open-source perception -> keep self-host relay path free.

## Unresolved Questions
- Monetize at all, or sponsor-funded with quotas?
- Merchant-of-record vs Stripe direct?
