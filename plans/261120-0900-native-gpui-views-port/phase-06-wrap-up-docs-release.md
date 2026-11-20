# Phase 06: Wrap-up

## Context Links
- `docs/project-changelog.md`, `docs/code-standards.md`, `README.md`
- Parent plan: `plans/261119-1749-native-gpui-desktop/plan.md`

## Overview
Priority P2 · Status todo.

## Requirements
- `WEB_VIEWS` keeps only views not ported; "Open in browser" stays as a secondary action.
- Changelog "Unreleased": native views list; README: native window section.
- Parent plan: update the line "Views not in the MVP ... open the web UI" and phase 3/4 status.
- `cargo clippy` + `cargo test -p drover-desktop-native -p drover-proto` once, capped.

## Todo List
- [ ] WEB_VIEWS trimmed
- [ ] docs + changelog
- [ ] parent plan updated
- [ ] final clippy + tests (capped)

## Success Criteria
- No button in drover-native opens the browser except "Open in browser" / "Edit in browser" and terminal links.

## Next Steps
Ask the user before commit / push / release.
