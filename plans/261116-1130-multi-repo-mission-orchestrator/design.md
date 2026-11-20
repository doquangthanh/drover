# Design: Missions, one task across many repos

Status: draft for review. Date: 2026-11-16. Nothing implemented.

## 1. Problem
One piece of work often touches several repos (API change in repo A, client change in repo B, docs in repo C).
Today the user does this by hand, or opens one Claude and prompts it to run `dr run --cwd ...` helpers.
What is missing (checked in code):

| Need | Today |
|---|---|
| A durable record of "this task = these repos, these branches, these agents" | none; the agent tree is built from live panes and an in-memory message log (`agent_messages_log.py`, 500 items) |
| A ready-made coordinator | none; the user must write the brief and run `dr skill` setup |
| One screen for the whole task (per-repo state, branch, diff size) | Agent tree (web) shows who started whom, but not repos, branches or changes as one unit |
| Survives a daemon restart | panes come back as *stopped* with **new ids** (`session_persistence.resume` calls `create_pane`), so any id-based link is lost |

Already there and reused: `parent` on panes, `OrchestrationPolicy` (max_panes 12, max_depth 3), `dr run --worktree`,
`worktree.create/changes/diff`, `dr prompt --wait`, Agent tree + Flow board (web), restore dialog, remote machines.

## 2. Concept
A **Mission** = goal + a **coordinator** agent + one **member** per repo (worktree + worker agent).

```
Mission "add promo codes"
 |- coordinator  (Claude, normal pane, in a scratch folder)   <- reads/writes MISSION.md, uses dr
 |- member api    repo ~/work/api     branch dr/promo-codes   worker pane (parent = coordinator)
 |- member web    repo ~/work/web     branch dr/promo-codes   worker pane
 `- member docs   repo ~/work/docs    branch dr/promo-codes   worker pane
```

## 3. Key decisions (recommended)
1. **Coordinator is an ordinary agent pane**, not a new LLM loop inside the daemon. It gets a generated brief plus the
   `dr` skill. Reuses policy, tree, restore, notifications. The daemon stores state and enforces limits; it does not think.
2. **Mission state lives in the daemon** (new `mission_store`, saved with the session file). Source of truth for
   membership; live state (working/blocked/done) is *derived* from member panes, never copied.
3. **One git worktree per member**, branch `dr/<mission-slug>` (existing `worktree.create`). A worker edits only its
   own worktree. Cross-repo requests go through the coordinator.
4. **Shared notes by file**: `<state dir>/missions/<id>/MISSION.md` (goal, plan, interface contracts, written by the
   coordinator) and `report-<repo>.md` (written by each worker). Env `DR_MISSION_DIR` is set in every member pane.
   Plain files = agents already know how to use them; no new protocol.
5. **Stable member id**, pane id is a pointer. On `session.resume` the daemon re-points the member whose
   `(space_id, name)` matches the stopped pane (needed because resume mints a new pane id).
6. **No automatic push, PR or merge.** Mission ends in `review`; the user (or a later feature) opens PRs per repo.
7. **Limits**: mission `max_members` (default 5) on top of global `max_panes` and `max_depth`; all existing prompts
   still go to the user (`agents_may_answer_permission_prompts = ask-user`).

## 4. Data model (daemon, JSON in session file)
```
Mission { id, name, goal, status: planning|running|review|done|cancelled, coordinator: pane_id|null,
          created_at, dir, members: [Member] }
Member  { id, repo_path, space_id, branch, base, worktree_path, name, pane_id|null, role_hint, report_path }
```
Derived per member: `state` (pane state or `stopped`), `changes` (files/+/-, via `worktree.changes`).
Derived mission "needs you" = any member or coordinator `blocked`.

## 5. API
RPC (new `rpc/methods_missions.py`, events `mission` in combined state):
`mission.create {name, goal, repos:[{path, role?}], coordinator?: command}`, `mission.list`, `mission.get`,
`mission.add_repo`, `mission.set_status`, `mission.note {text}` (append to MISSION.md), `mission.close {remove_worktrees?}`.

CLI: `dr mission new "goal" --repo PATH [--repo PATH ...]`, `dr mission ls`, `dr mission status [ID]`,
`dr mission add-repo PATH`, `dr mission done` (called by the coordinator), `dr mission close ID`.
`dr skill` gets a short "Missions" section (what `DR_MISSION_DIR` is, report format, when to call `dr mission done`).

`mission.create` flow: validate repos (git, clean enough) -> create worktrees -> write MISSION.md skeleton -> start
coordinator in the mission dir with the brief -> coordinator starts workers with `dr run --worktree` / `--cwd` or the
daemon starts them (decision Q2).

## 6. UI
Web, new view **Missions** next to Agent tree:
- Left: missions with roll-up glyph (reuse state glyphs). Create dialog: goal, repo multi-select from spaces
  (or folder picker), coordinator agent (default claude), "Start".
- Right: goal, members table (repo, branch, state, changes +/-, open pane, open diff), coordinator row, MISSION.md
  preview, and the existing Flow board filtered to the mission's panes.
- Actions: nudge coordinator (`dr prompt`), mark review/done, close (confirm, removes only clean worktrees).
TUI parity later: a "Missions" group in the sidebar and a members list; no new rendering code needed for panes.

## 7. Phases (rough, each shippable)
1. Daemon: mission model + store + RPC + restore re-pointing + policy `max_members`. Tests with `daemon_harness`.
2. CLI `dr mission ...` + skill text + brief template for the coordinator.
3. Web Missions view (list, detail, create dialog), reuse Flow board.
4. Polish: needs-you notifications per mission, close/cleanup, remote machines as members, TUI parity.

## 8. Risks
- Coordinator quality depends on the brief and the model; mitigate with a tight template and `MISSION.md` contract section.
- Resume re-pointing by `(space_id, name)` breaks if the user renames a pane; fall back to asking in the restore dialog.
- Worktree sprawl: cleanup must refuse dirty trees (existing `worktree.remove` already does).
- Cost/runaway: limits + visible roll-up; add per-mission "stop all" first.
- Cross-repo dependencies (B needs A's new API): v1 relies on the coordinator ordering work; no scheduler.

## 9. Out of scope (v1)
Auto PR/merge, cross-repo CI, scheduling/DAG engine, mission templates, sharing a mission between users.

## 10. Open questions
- Q1: is a mission always git-worktree based, or may a member just use the repo folder directly (no isolation)?
- Q2: who starts the workers: the coordinator (flexible, uses `dr run`) or the daemon at create time (predictable)?
- Q3: coordinator location: a scratch folder (clean) or inside one of the repos (can see code, risks edits)?
- Q4: should the first slice include the web UI, or ship CLI + daemon first and use the existing Agent tree to watch?
