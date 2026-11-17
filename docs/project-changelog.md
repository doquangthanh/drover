# Changelog

## 0.1.31
### Changed
- The terminal UI (`dr`) looks like Herdr's: sidebar entries are two lines (state and name; branch, `↑` commits
  ahead, `±` changed files), long names end in "…", and the open space and focused agent are highlighted (the
  cursor shows only while you move through the sidebar). Tabs are blocks with the open one in the accent colour, a
  clickable `+` and the key hint on the right. A tab's only pane fills it without a frame; split panes get frames.
  State colours match the web UI.
### Fixed
- Linux desktop window: terminal text no longer looks letter-spaced. In Qt WebEngine xterm's WebGL renderer drew a
  small fallback font whatever the terminal font; the window now uses the DOM renderer (browsers keep WebGL).
- After a restart each Claude pane resumes its own conversation (`claude --resume <id>`, read from Claude Code's
  session file) instead of the folder's newest one (`--continue`), so two Claude panes in one repo no longer come
  back as the same conversation. Linux/macOS; elsewhere `--continue` as before.

## 0.1.30
### Added
- Terminal font like a terminal app: by default Drover's terminals use your system terminal's font (on Linux the
  GNOME Terminal profile font, else the desktop monospace font, e.g. Ubuntu Mono 13 pt = 17 px) instead of the
  browser's monospace. Pick another font and size in Settings > Appearance > Terminal font (installed monospace fonts
  are listed; kept per device). New RPC `fonts.list`.

## 0.1.29
### Changed
- The terminal UI (`dr` / `dr tui`) works like Herdr: prefix **Ctrl+B** (new setting `tui_prefix`; the web UI keeps
  `prefix`, Ctrl+A) and Herdr's keys: `c` new tab, `n`/`p` next/previous tab, `1-9` tabs of the current space,
  `T`/`X` rename/close tab, `N`/`W`/`D` new/rename/close space, `v`/`-` split, `h j k l` move, `H J K L` swap,
  `g` goto picker, `w`/`b` sidebar, `[` scroll/copy mode, `q` detach. Drover extras: `a` next agent that needs you,
  `r` restore.
- Sidebar shows spaces on top and agents below (plain shells are hidden); a tab bar above the panes.
- With no space yet, the TUI opens one in the current folder.
### Added
- Pane scrollback in the TUI: mouse wheel or copy mode (`y` copies the visible lines).
### Fixed
- A tab created with `tab.create` now reaches clients under its real name instead of "tab".

## 0.1.28
### Changed
- Agents are detected like Herdr: from the program that holds a shell pane's terminal (foreground process group),
  not from the terminal title. Typing `claude`, `codex`, `gemini` or `opencode` turns the pane into that agent;
  quitting back to the prompt turns it into a shell again (and hides it from Agents). Windows keeps the title check.
- "+" in the tab bar, `Ctrl+N` and `Ctrl+A c` open a new terminal instead of the agent picker.
- A new space starts in the folder the focused pane is in now (home when unknown).
- A space is named after the folder its first pane is in and follows `cd`, unless you renamed it.

## 0.1.27
### Changed
- New space works like herdr: no folder or agent picker. "+" / "New space" opens a fresh space with a shell in the
  home folder. Run `claude`, `codex`, `gemini` or `opencode` in it and the pane shows up under Agents; plain shells
  stay out of the Agents list.
- `space.create`: `cwd` is optional (defaults to home); `new: true` always makes a fresh space, even for a folder
  that already has one (named `folder-2`, `folder-3`, ...).

## 0.1.26
### Fixed
- Release builds now bundle Textual (`uv sync --extra tui` in CI), so plain `dr` from `install.sh` opens the terminal
  UI instead of the desktop window.

## 0.1.25
### Changed
- Plain `dr` now opens the terminal UI when Textual is installed (`pip install 'drover[tui]'`). `dr app` still opens
  the desktop window, and `dr` falls back to it when Textual is missing.

## 0.1.24
### Added
- `dr tui`: terminal UI in your own terminal (Textual). Sidebar with spaces, tabs and agent states, split panes with
  live terminals, tmux-style prefix keys (`Ctrl+A`, same as the web UI), a restore dialog for panes from the previous
  session and a layout that adapts to narrow terminals. Needs the optional extra: `pip install 'drover[tui]'`.
  The daemon and web UI are unchanged; `dr` without arguments still opens the desktop window.

## 0.1.23
### Added
- In-app update shows a full-screen "Updating Drover..." cover until the server is back and the page reloads.
### Fixed
- After an in-app update the new daemon keeps the old port and token, and the page reloads once the connection
  returns. Before, a browser tab stayed on the dead address with every agent showing "exit" and the
  "Pick up where you left off?" dialog never appeared.
- An agent started by typing `claude` (or another agent) inside a shell pane now remembers its resume command, so
  "Resume" after a restart continues the conversation (`claude --continue`) instead of opening a fresh one.

## 0.1.22
### Changed
- Terminal and mono text in the web UI use the system default monospace font instead of the bundled JetBrains Mono.

## 0.1.21
### Fixed
- Desktop app (Windows): clicking a link in a terminal pane (plain URLs and Claude Code's OSC 8 links) showed
  "Get an app to open this 'about' link" instead of opening the browser. Links now open in the default browser;
  only http(s) links are opened.

## 0.1.20
### Changed
- Windows: `dr` calls from agent panes and Claude hooks start about 2x faster (measured `dr ls`: ~390 ms -> ~190 ms).
  Each release now also ships `drover-cli-windows-x64.zip`, an unpacked `dr.exe`. The daemon downloads it once per
  version in the background into `<state dir>/runtime/<version>/`, and the `dr` shim uses it as soon as it is
  there. Offline, or if anything fails, `dr` keeps using drover.exe. `drover.exe` is still the only download.
- Packaged builds leave out setuptools / pkg_resources: PyInstaller's setuptools start-up hook imported it (~0.5 s
  in source Python) on every start, while nothing in drover uses it.
### Fixed
- The `dr.cmd` / `hd.cmd` shims were written with doubled carriage returns (`\r\r\n`) and rewritten on every
  pane start; now byte-exact and written only when they change.
- In-app update: a download cut off mid-way (`IncompleteRead`) now fails cleanly instead of with an unexpected error.

## 0.1.19
### Added
- Flow board shows Claude Code sub-agents (Task/Agent tool: planner, tester, ...) as their own lanes under the
  `claude` pane that runs them, with "delegates" / "returned" arrows (with the sub-agent's last message) and a live
  bar. No extra panes, no extra tokens: drover starts `claude` with `--settings <state dir>/claude-subagent-hooks.json`
  (SubagentStart / SubagentStop hooks running the silent `dr hook claude`); `~/.claude/settings.json` is untouched.
  Turn it off with `claude_subagent_hooks = false` in settings.toml. Panes started before the update get it on restart.
### Fixed
- Agent tree Flow board: an agent that exits (a one-shot `dr run claude -p ...`, a finished command) now gets an
  "exited" event with its exit code to its parent (or you), and its activity bar ends there; before, nothing was logged.
- `dr wait <helper> --state done` hung until its timeout when the helper finished while its pane was focused (a
  focused pane goes working → idle, never "done"); that transition now ends the wait, and the Flow board logs it as
  "finished".
- Agent tree events keep at most 500 characters of text, so a long prompt no longer stays in memory in full and goes
  out in every `messages.list` reply.

## 0.1.18
### Changed
- Agent tree Flow board shows every agent, not only helpers started with `dr run`: agents you start get a
  "you started" event, and a "needs you" / "finished" event to you when they block or finish.
### Fixed
- Vietnamese (and other non-ASCII) prompts piped to `dr prompt <agent> -` on Windows no longer arrive as mojibake
  in the agent and the agent tree: the CLI now reads stdin as UTF-8, not cp1252.
- Chat panel on Windows no longer opens a console window for the Agent SDK's `claude.exe` child.

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
