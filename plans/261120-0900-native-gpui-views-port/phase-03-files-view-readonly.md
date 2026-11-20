# Phase 03: Files view (view-only)

## Context Links
- Web: `frontend/src/files/{use-files-data.ts,file-tree.tsx,file-tree-row.tsx,file-icon.tsx,files-view.tsx}`
- Diff rendering reused from phase 02 (`views/changes/diff_view.rs`)

## Overview
Priority P2 · Status todo · Decision: view-only (no editor) in v1.

## Key Insights
- `files.list {space, path}` → `{entries: [{name, path, dir}]}`; `files.read {space, path}` →
  `{text, binary, size, error, mtime_us, editable, why_readonly}`; git status per path; diff via
  `worktree.diff {path: space.cwd, base: "HEAD", file}` for status M/A/D/R.
- Web polls every 3 s while mounted; native does the same only while Files is the shown view.

## Requirements
- Left: lazy folder tree (expand on click), file icons by extension, git status colour.
- Right: file text with line numbers, monospace, select/copy, virtual rows; "Diff" toggle for changed files.
- Binary / too big / error states. "Edit in browser" button (opens web `#files`).
- Syntax colours: decide in step 1 (syntect vs none).

## Architecture
```
views/files/mod.rs     split(tree | content)
views/files/data.rs    dirs map, status map, open file, poll timer
views/files/tree.rs    rows + icons
views/files/content.rs text rows / diff rows (shared with changes)
```

## Related Code Files
- Modify: `views/mod.rs`, `Cargo.toml` (only if syntect chosen)
- Create: files above

## Implementation Steps
1. Spike: syntect build cost under cap (time, RAM, binary size). If > ~2 min or > +5 MB, ship plain text.
2. Tree + lazy load + status.
3. Content view with virtual rows + select/copy (reuse terminal_selection ideas).
4. Diff toggle, polling, states.
5. Build, screenshot vs web `#files`.

## Todo List
- [ ] syntect spike decision
- [ ] tree
- [ ] content view
- [ ] diff toggle + polling
- [ ] Build, test, screenshot

## Success Criteria
- Browse this repo, open a 5k-line file smoothly, copy text, see diff of a changed file.

## Risk Assessment
- Selection across virtual rows: keep selection in (line, col) model, not in painted rows.

## Security Considerations
- Read-only; paths come from the daemon listing, no free path input.

## Next Steps
Phase 04 (Inbox). Later plan: native editor.
