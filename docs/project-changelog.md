# Changelog

## Unreleased
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
