# Drover

A personal workspace for running coding agents (Claude Code, Codex, Gemini, opencode, any shell),
inspired by [Herdr](https://github.com/herdrdev/herdr). Python daemon + web UI in a native window.

- **Agents keep running** in `drover-server` when you close the window; reopen and they are still there.
- **See who needs you**: each agent is *working*, *needs you*, *done* or *idle*, detected from its screen
  with TOML rules (or reported by the agent via OSC 7501). Desktop + in-app notifications.
- **Agents run agents**: `dr run --bg`, `dr wait`, `dr read`, `dr send` from inside any pane.
- **Every machine in one sidebar**: remote daemons over SSH (`dr machine add`).
- **Git worktrees** per task, Changes view with diff / commit / push / PR.
- **Plain-file config** (settings, keys, detection rules) editable in the app.
- **Phone**: the same UI is responsive; open it over Tailscale or an SSH tunnel.

## Install (Linux, one line)

```sh
curl -fsSL https://raw.githubusercontent.com/doquangthanh/drover/main/scripts/install.sh | sh
```

Downloads the latest release (x64/arm64) into `~/.local/share/drover` and links `dr` and `drover` into `~/.local/bin`.
No Python or Node needed. Without GTK/WebKit there is no native window; `dr` opens the web UI in your browser.
Re-run the command to update. `DROVER_VERSION=v0.1.0` pins a version.

## Install from source (Windows, also works on Linux/macOS)

```powershell
# once: uv + Python 3.12
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
cd drover
uv sync
uv run drover            # opens the window (starts drover-server if needed)
```

Put `dr` on your PATH with `uv tool install --editable .` (then `dr` / `drover` work anywhere).

### Web UI (React) build

The UI is a Vite + React + TypeScript app in `frontend/`; the daemon serves its build from `src/drover/web_dist/`
(gitignored). Build it once before running from a checkout (needs Node 20.19+ or 22+):

```
npm --prefix frontend ci
npm --prefix frontend run build      # -> src/drover/web_dist/, served at / (and /ui/)
```

Without it the daemon answers `503 UI not built`. For UI work run the daemon, then `npm --prefix frontend run dev`:
the dev server (http://localhost:5173/ui/?token=...) proxies `/ws`, `/rpc`, `/static` and `/health` to the running
daemon (read from `daemon.json`; override with `DROVER_STATE_DIR`). Checks: `npm --prefix frontend run typecheck`
and `npm --prefix frontend test`.

### Windows app (.exe, no Python needed)

```powershell
npm --prefix frontend ci; npm --prefix frontend run build   # the spec refuses to build without web_dist
uv run pyinstaller packaging/drover.spec --noconfirm
```

Output: a single `dist\drover.exe` (~30 MB). Run it for the window; `drover <cmd>` is the CLI (`drover status`, ...) and the
background server. Agent panes get an `dr` shim on PATH.
Copy the file anywhere.
Needs the WebView2 runtime (built into Windows 10/11).

## Everyday use

| Want to | Do |
|---|---|
| Start an agent | `+` in the tab bar, or **Ctrl+A c**. Pick agent, folder (**Choose…** opens the Windows folder picker), optional worktree and first prompt |
| Jump to whoever needs you | **Ctrl+A n**, or the Inbox |
| Find any agent or text | **Ctrl+A /** |
| All commands | **Ctrl+A :** — all shortcuts: **Ctrl+A ?** |
| Split / zoom / close | **Ctrl+A %**, **Ctrl+A "**, **Ctrl+A z**, **Ctrl+A x** |

The prefix is Ctrl+A (tmux style). Press Ctrl+A twice to send a real Ctrl+A to the agent.

## CLI (`dr`)

```
dr run [--bg] [--name N] [--cwd DIR] [--on MACHINE] [--worktree TASK] -- claude
dr ls [--json]            dr read NAME [--lines 60]      dr send NAME "text"
dr wait NAME --state done --timeout 900                  dr attach NAME   (Ctrl+\ detaches)
dr kill NAME [--tree]     dr status                      dr schema / dr skill
dr server start|stop|restart|logs|url|autostart on|off
dr machine add vps-1 deploy@vps-1 [--install] | ls | rm | test
dr worktree new TASK [--run claude] | ls | rm PATH [--force]
dr rules ls | test NAME
```

Exit codes: 2 timeout, 3 not found, 4 refused by policy, 10 server unavailable.
`dr skill >> AGENTS.md` teaches an agent how to use Drover.

## Remote machines

`dr machine add vps-1 deploy@vps-1.tail-net --install` installs uv + Drover there (Linux/macOS; build the
wheel first with `uv build --wheel`), starts its daemon and connects through an SSH tunnel. The remote
daemon only listens on 127.0.0.1. Host keys are checked against `known_hosts`.

## Phone

The web UI has a phone layout (screens up to 760 px wide): a bottom tab bar (Agents, Inbox, Files, Changes, More),
one full-screen terminal at a time with a key strip (Esc, Tab, arrows, Ctrl+C, Paste…) and a message box, a file
tree + code editor, and dialogs as bottom sheets. Everything on the desktop is reachable from it.

Simplest: SSH into this computer from the phone and run `dr attach NAME`.
For the full UI over Tailscale: `dr server stop`, then `dr server run --listen <tailscale-ip>`,
and open the link printed by `dr server url`. Anyone with that link controls your agents — keep it private.

## Config

Files live in `%APPDATA%\drover` (Linux: `~/.config/drover`): `settings.toml`, `keys.toml`, `machines.toml`,
`rules/*.toml`, plus `AGENTS.md` explaining them. Logs and session state: `%LOCALAPPDATA%\drover`.

## Security notes

- The daemon binds 127.0.0.1 with a random port and a random token stored in an owner-only file.
- Any program running inside a Drover pane can control all panes through `dr` (same as Herdr).
- Agents cannot answer another agent's permission prompt unless you allow it
  (`orchestration.agents_may_answer_permission_prompts`).

## Licenses

drover: Apache-2.0. Uses xterm.js (MIT, npm `@xterm/*`; license copy in `src/drover/web/vendor/LICENSE-xterm.txt`).
Detection rules are inspired by Herdr's `distribution/agent-detection` (Apache-2.0).
