# Phase 04: Parity gate in CI + docs

## Context
- New `.github/workflows/ci.yml` (none today: only release workflows), `docs/code-standards.md`,
  `docs/system-architecture.md`, `README.md`

## Overview
Priority P1. Status todo. Stop drift: every push builds and tests on Windows and Linux; a rule for new code.

## Key insights
- Drift happened because Windows-only and Linux-only code paths were never compiled on the other OS
  (0.1.41 Linux build broke on a `#[cfg(unix)]` closure nobody built on Windows).

## Requirements
- `ci.yml` on push/PR, matrix ubuntu + windows: `cargo build --workspace`, `cargo test -p drover-core
  -p drover-daemon`, daemon conformance suite, pytest, frontend build.
- Rule in `docs/code-standards.md`: platform code only as a shim below one shared function; no feature behind
  `cfg!(windows)` / `sys.platform`; new feature = tests on both runners.

## Related code files
- Create: `.github/workflows/ci.yml`. Modify: `docs/code-standards.md`, `docs/system-architecture.md`,
  `README.md` (one install section shape for both), `docs/project-changelog.md`.

## Todo
- [ ] ci.yml matrix
- [ ] code-standards parity rule
- [ ] architecture + README update
- [ ] changelog

## Success criteria
A PR that breaks either OS fails CI before a tag; README describes one product, two install commands.

## Risks
CI minutes: cache cargo (`Swatinem/rust-cache`), which also speeds release builds.
