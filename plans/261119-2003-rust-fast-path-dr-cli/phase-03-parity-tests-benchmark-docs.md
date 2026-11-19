# Phase 03: Parity tests, benchmark, docs

## Overview
Priority P1. Status: todo.

## Requirements
- Parity test: scratch daemon (separate `DROVER_STATE_DIR`), shell panes only; run each native command form via
  Rust `dr` and Python `dr`; compare stdout, stderr, exit code byte for byte. Skipped when
  `DROVER_TEST_FAST_DR_BIN` is not set.
- Benchmark vs herdr with `bench-drover-vs-herdr.ps1` method; record in `plans/reports/`.
- Docs: changelog, `docs/system-architecture.md` (CLI section), `docs/code-standards.md` if Rust notes change;
  update rust-full-rewrite plan phase 06 status.

## Todo List
- [ ] parity test  - [ ] benchmark report  - [ ] docs

## Success Criteria
Parity test green; `dr ls`/`read`/`send` medians within ~10 ms of herdr.
