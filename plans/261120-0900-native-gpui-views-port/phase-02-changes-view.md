# Phase 02: Changes view

## Context Links
- Web: `frontend/src/changes/*` (use-changes-data.ts, use-worktree-actions.ts, worktree-list.tsx, diff-parse.ts, diff-view.tsx)
- Test to port: `changes/diff-parse.test.ts`

## Overview
Priority P1 · Status todo · ~500 lines to port.

## Key Insights
- Data (space cwd, `machine` added when the space is remote):
  `git.info {path}`, `worktree.list {repo}`, `worktree.changes {path, base}`, `worktree.diff {path, base, file}`.
- Base = chosen base or first worktree's branch or `main`. Default worktree = second live one, else first.
- Actions: `git.push {path}` then `git.pr {path}`; `worktree.remove {path, force?}`; `worktree.prune {repo}`.

## Requirements
- Left: worktree list (branch, change count, missing marked), base picker.
- Middle: changed files (status letter, +added / −removed).
- Right: unified diff of the selected file, green/red lines, line numbers, hunk headers; select/copy.
- Not a repo / error / empty states. Refresh button; refresh when the space's `dirty` changes.
- Actions with confirm for remove/force; result output shown in a small panel.

## Architecture
```
views/changes/mod.rs        3-column split
views/changes/data.rs       RpcCells: info, trees, files, diff; selection
views/changes/diff_parse.rs port of diff-parse.ts (+ tests)
views/changes/diff_view.rs  uniform_list of diff rows
views/changes/actions.rs    push/PR, remove, prune
```

## Related Code Files
- Modify: `views/mod.rs`, `topbar.rs` (status-bar branch chip opens Changes)
- Create: files above

## Implementation Steps
1. Diff parse port + tests.
2. Data loading chain (info + list in parallel, then changes, then diff on select).
3. Three columns + states.
4. Diff view with virtual rows.
5. Actions + confirm + output.
6. Build, screenshot vs web `#changes`.

## Todo List
- [ ] diff_parse + tests
- [ ] data chain
- [ ] columns + states
- [ ] diff view
- [ ] actions
- [ ] Build, test, screenshot

## Success Criteria
- Same files and diff as web for this repo's worktrees; 5k-line diff scrolls smoothly.

## Risk Assessment
- Remote machines: pass `machine` param like the web; test only locally if no remote is set up (report "not run").

## Security Considerations
- Remove / force remove are destructive: confirm with path shown. Push/PR: confirm with branch shown.

## Next Steps
Phase 03 (Files).
