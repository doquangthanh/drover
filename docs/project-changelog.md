# Changelog

## Unreleased
### Changed
- Agent tree Flow board shows every agent, not only helpers started with `dr run`: agents you start get a
  "you started" event, and a "needs you" / "finished" event to you when they block or finish.
### Fixed
- Vietnamese (and other non-ASCII) prompts piped to `dr prompt <agent> -` on Windows no longer arrive as mojibake
  in the agent and the agent tree: the CLI now reads stdin as UTF-8, not cp1252.

## 0.1.17
### Fixed
- Windows in-app update no longer fails with "an older drover.exe.old is still in use" when a window or daemon from
  an earlier update is still running: the running exe moves to drover.exe.old2, .old3... instead, and every leftover
  .old copy is removed on the next start once nothing runs it.

## 0.1.16
### Changed
- Agent tree redesigned. The tree draws real connector lines, shows each agent's title, a state badge and a name
  filter. The selected agent gets a header with its tree's counts (helpers, working, needs you, done), a progress
  bar and an "Answer" banner for every helper waiting for you.
- New Flow tab (the default): one swimlane per agent of the selected tree, an arrow per `dr run` / `dr send` /
  `dr wait` / done / needs-you / denied event from `messages.list`, and a bar showing when each helper was active.
  Selecting a helper dims what it was not part of. Messages and Policy stay as tabs.

## 0.1.15
### Changed
- Sidebar is back to two halves, Spaces (grouped by machine) and Agents (grouped by space); the single workspace
  tree of 0.1.14 is gone, along with its collapse state, the machine picker on "+", the top-bar workspace title and
  the new-workspace toast. "Workspace" is "Space" again in the UI.
- Chats are listed inside the Agents section, under the space with the same folder (others last), instead of a
  separate "Chats" group.

## 0.1.14
### Changed
- Sidebar is one tree of workspaces: each workspace lists its agents under it and collapses (chevron or ←/→,
  remembered per device), with a dot that still shows when a collapsed agent needs you. The separate Agents list is gone.
- Remote workspaces sit in the same list with a machine chip and its link state; "+" asks which machine when one is
  connected.
- A workspace with a single tab shows its name and folder in the top bar instead of a lone tab.
- A toast names any workspace that appears without being opened from the UI (for example an agent started from the
  CLI in a new folder), with a Rename action.
- "Space" is now "Workspace" everywhere in the UI.

## 0.1.13
### Changed
- In-app toasts redesigned: tone-coloured accent bar and badge (needs you, done, error, update, stopped), an action
  button ("Answer", "Open", "Update"), a countdown bar that pauses on hover, longer lifetime for "needs you", at most
  four on screen. The Inbox side panel sample uses the same card.
- Desktop notifications now say what happened and what the agent was doing (agent name plus the terminal title), use a
  critical urgency for "needs you", and group per pane.

## 0.1.12
### Fixed
- "Check for updates" failed once GitHub's API rate limit (60 calls/hour per IP) was used up; it now falls back to
  the tag that github.com/<repo>/releases/latest redirects to.

## 0.1.11
### Added
- In-app update on Windows: Settings → Updates downloads the release `drover.exe`, checks it is a real program,
  renames the running file to `drover.exe.old`, puts the new one in its place and restarts the server; the `.old`
  copy is removed on the next start.
- The UI checks for a new release 15 s after start and every 12 h, and shows a toast (once per version) that opens
  Settings → Updates.

## 0.1.10
### Added
- `dr prompt NAME "text" [--wait]` (`pane.prompt`): submits a prompt (bracketed paste when the app enabled it), refuses
  an agent on a permission prompt without typing (exit 6, `agent_blocked`), reports `agent_prompt_stalled` (exit 7) when
  the screen shows no work within 5 s, otherwise waits for the turn to settle.
- `dr keys NAME esc up enter ctrl+c shift+tab ...` (`pane.keys`): named keys, under the same permission-prompt policy as
  `dr send`.
- `dr wait-output NAME PATTERN [--regex] [--lines N]` (`pane.wait_output`): wait for text in any pane's recent output.
- `dr read --lines N` on a full-screen agent (alternate screen + SGR mouse, e.g. OpenCode) scrolls the agent's own
  viewport with wheel events, joins the pages once (fixed header/footer kept once) and scrolls back to the bottom.
  Only for idle/done agents.
- `dr rename` (`pane.rename` now returns `{pane, name}` and rejects duplicate names or names with `/` or `:`).
- Layout from scripts, all printing JSON with the ids they create: `dr space new|ls`, `dr tab new|ls|rename|close`
  (`tab.create`), `dr pane split|move|swap|zoom|unzoom|share|focus` (`pane.split`, `pane.move`, `pane.swap`,
  `pane.zoom`, `pane.share`).
- `dr completion bash|zsh|fish|powershell`, generated from the argparse tree; agent names come from `dr ls --names`,
  which never starts the daemon.

### Fixed
- A pane could stay `working` forever after `dr send`: when a quick command went quiet before the 3 s post-input hold
  ended, the monitor stopped re-evaluating it, so `dr wait` timed out. The monitor now keeps checking until the hold
  has debounced.

### Changed
- Renamed herd to Drover everywhere: Python package `drover`, window/app `drover` (`drover.exe` on Windows), CLI `dr`
  (`hd` stays as an alias), env vars `DROVER_*`, pane env `DR_PANE_ID`, worktree branches `dr/<task>`, release assets
  `drover.exe` / `drover-linux-<arch>.tar.gz`, GitHub repo `doquangthanh/drover`. Old `herd` config/state folders and
  the sign-in autostart entry move over automatically on first start; the Linux installer removes an old herd install.
- Web UI rewritten as Vite + React + TypeScript + Zustand (`frontend/`). Same layout, CSS and shortcuts; the sidebar,
  top bar and status bar no longer rebuild on every state event, Ace and the xterm WebGL addon load lazily.
- `/` now serves the built UI from `src/drover/web_dist/` (also reachable at `/ui/`); hashed assets are cached as immutable,
  `index.html` stays `no-store`. Missing build answers `503 UI not built`.
- Building from source needs Node 20.19+ or 22+: `npm --prefix frontend ci && npm --prefix frontend run build`.
- `packaging/drover.spec` bundles `web_dist/` and fails fast when it is missing; the wheel includes it via hatch `artifacts`.

### Removed
- Legacy vanilla-JS UI (`src/drover/web/js`, `index.html`) and vendored xterm files (xterm now comes from npm `@xterm/*`).
- CSS and fonts moved to `frontend/src/styles/` (content unchanged).

### Fixed
- Layout tree type in the frontend matches the daemon (`split`, not `dir`).
