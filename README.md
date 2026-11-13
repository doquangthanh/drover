# herd

A personal workspace for running coding agents (Claude Code, Codex, Gemini, opencode, any shell),
inspired by [Herdr](https://github.com/herdrdev/herdr). Python daemon + web UI in a native window.

- **Agents keep running** in `herd-server` when you close the window; reopen and they are still there.
- **See who needs you**: each agent is *working*, *needs you*, *done* or *idle*, detected from its screen
  with TOML rules (or reported by the agent via OSC 7501). Desktop + in-app notifications.
- **Agents run agents**: `hd run --bg`, `hd wait`, `hd read`, `hd send` from inside any pane.
- **Every machine in one sidebar**: remote daemons over SSH (`hd machine add`).
- **Git worktrees** per task, Changes view with diff / commit / push / PR.
- **Plain-file config** (settings, keys, detection rules) editable in the app.
- **Phone**: the same UI is responsive; open it over Tailscale or an SSH tunnel.

## Install (Windows, also works on Linux/macOS)

```powershell
# once: uv + Python 3.12
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
cd herd
uv sync
uv run herd            # opens the window (starts herd-server if needed)
```

Put `hd` on your PATH with `uv tool install --editable .` (then `hd` / `herd` work anywhere).

### Windows app (.exe, no Python needed)

```powershell
uv run pyinstaller packaging/herd.spec --noconfirm
```

Output: `dist\herd\` (~50 MB). Run `herd.exe` for the window; `hd.exe` is the CLI and background server.
Copy the whole folder anywhere; agent panes get it on their PATH so `hd` works inside them.
Needs the WebView2 runtime (built into Windows 10/11).

## Everyday use

| Want to | Do |
|---|---|
| Start an agent | `+` in the tab bar, or **Ctrl+B c**. Pick agent, folder (**Choose…** opens the Windows folder picker), optional worktree and first prompt |
| Jump to whoever needs you | **Ctrl+B n**, or the Inbox |
| Find any agent or text | **Ctrl+B /** |
| All commands | **Ctrl+B :** — all shortcuts: **Ctrl+B ?** |
| Split / zoom / close | **Ctrl+B %**, **Ctrl+B "**, **Ctrl+B z**, **Ctrl+B x** |

The prefix is Ctrl+B (tmux style). Press Ctrl+B twice to send a real Ctrl+B to the agent.

## CLI (`hd`)

```
hd run [--bg] [--name N] [--cwd DIR] [--on MACHINE] [--worktree TASK] -- claude
hd ls [--json]            hd read NAME [--lines 60]      hd send NAME "text"
hd wait NAME --state done --timeout 900                  hd attach NAME   (Ctrl+\ detaches)
hd kill NAME [--tree]     hd status                      hd schema / hd skill
hd server start|stop|restart|logs|url|autostart on|off
hd machine add vps-1 deploy@vps-1 [--install] | ls | rm | test
hd worktree new TASK [--run claude] | ls | rm PATH [--force]
hd rules ls | test NAME
```

Exit codes: 2 timeout, 3 not found, 4 refused by policy, 10 server unavailable.
`hd skill >> AGENTS.md` teaches an agent how to use herd.

## Remote machines

`hd machine add vps-1 deploy@vps-1.tail-net --install` installs uv + herd there (Linux/macOS; build the
wheel first with `uv build --wheel`), starts its daemon and connects through an SSH tunnel. The remote
daemon only listens on 127.0.0.1. Host keys are checked against `known_hosts`.

## Phone

The web UI has a phone layout (screens up to 760 px wide): a bottom tab bar (Agents, Inbox, Files, Changes, More),
one full-screen terminal at a time with a key strip (Esc, Tab, arrows, Ctrl+C, Paste…) and a message box, a file
tree + code editor, and dialogs as bottom sheets. Everything on the desktop is reachable from it.

Simplest: SSH into this computer from the phone and run `hd attach NAME`.
For the full UI over Tailscale: `hd server stop`, then `hd server run --listen <tailscale-ip>`,
and open the link printed by `hd server url`. Anyone with that link controls your agents — keep it private.

## Config

Files live in `%APPDATA%\herd` (Linux: `~/.config/herd`): `settings.toml`, `keys.toml`, `machines.toml`,
`rules/*.toml`, plus `AGENTS.md` explaining them. Logs and session state: `%LOCALAPPDATA%\herd`.

## Security notes

- The daemon binds 127.0.0.1 with a random port and a random token stored in an owner-only file.
- Any program running inside a herd pane can control all panes through `hd` (same as Herdr).
- Agents cannot answer another agent's permission prompt unless you allow it
  (`orchestration.agents_may_answer_permission_prompts`).

## Licenses

herd: Apache-2.0. Bundles xterm.js (MIT, `src/herd/web/vendor/LICENSE-xterm.txt`).
Detection rules are inspired by Herdr's `distribution/agent-detection` (Apache-2.0).
