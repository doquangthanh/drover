<p align="center">
  <img src="packaging/brand/drover-readme-banner.svg" alt="Drover: keep the whole herd moving" width="100%">
</p>

<p align="center">
  <a href="https://github.com/doquangthanh/drover/releases/latest"><img alt="Latest release" src="https://img.shields.io/github/v/release/doquangthanh/drover?style=flat-square&color=96b2d7&label=release"></a>
  <img alt="Windows, Linux, macOS" src="https://img.shields.io/badge/runs%20on-Windows%20%C2%B7%20Linux%20%C2%B7%20macOS-1d1f23?style=flat-square">
  <img alt="Apache-2.0" src="https://img.shields.io/badge/license-Apache--2.0-4cc48c?style=flat-square">
  <a href="https://github.com/doquangthanh/drover/actions"><img alt="Build" src="https://img.shields.io/github/actions/workflow/status/doquangthanh/drover/release-windows.yml?style=flat-square&label=build"></a>
</p>

<p align="center">
  <a href="https://github.com/doquangthanh/drover/releases/latest/download/drover.exe"><img alt="Download for Windows" src="https://img.shields.io/badge/Download-Windows%2010%20%2F%2011-76a8ff?style=for-the-badge&logo=windows&logoColor=white&labelColor=1c2147"></a>
  &nbsp;
  <a href="#linux"><img alt="Install on Linux" src="https://img.shields.io/badge/Install-Linux-4cc48c?style=for-the-badge&logo=linux&logoColor=white&labelColor=1c2147"></a>
</p>

<p align="center"><a href="https://doquangthanh.github.io/drover/"><b>doquangthanh.github.io/drover</b></a></p>

---

## What is Drover?

**Drover is one workspace for every AI coding agent you run.** Start Claude Code, Codex, Gemini, opencode or a plain
shell side by side. Drover keeps them running in the background, shows at a glance which one is working, which one is
waiting for you and which one is done, and lets you answer, review and ship their work from one window, on any of
your machines.

Run five agents at once without babysitting five terminals.

| | State | What it means |
|:-:|---|---|
| 🔵 | **Working** | The agent is busy. Leave it alone. |
| 🟠 | **Needs you** | It is asking a question or waiting for permission. You get a notification. |
| 🟢 | **Done** | It finished. Review the changes when you are ready. |
| ⚪ | **Idle** | Nothing is running in that pane. |

## Why teams use it

<table>
<tr>
<td width="50%" valign="top">

**Agents keep running**<br>
Close the window and they carry on in `drover-server`. Reopen it tomorrow and everything is where you left it.

</td>
<td width="50%" valign="top">

**Knows who needs you**<br>
State comes from each agent's screen (plain TOML rules) or from the agent itself over OSC 7501. Desktop
notifications and an Inbox of everyone waiting.

</td>
</tr>
<tr>
<td valign="top">

**Agents run agents**<br>
`dr run`, `dr wait`, `dr read` and `dr send` work from inside any pane, so one agent can hand work to another and
wait for the result.

</td>
<td valign="top">

**A git worktree per task**<br>
Every task gets its own worktree and branch. The Changes view shows the diff and lets you commit, push and open a PR.

</td>
</tr>
<tr>
<td valign="top">

**Every machine in one sidebar**<br>
Add a server with `dr machine add`. Its agents appear next to your local ones through an SSH tunnel.

</td>
<td valign="top">

**Chat view for Claude Code**<br>
Read Claude's work as a conversation with tool cards, approve permissions inline, switch model and autonomy level.

</td>
</tr>
<tr>
<td valign="top">

**Works on your phone**<br>
The same UI has a phone layout with a key strip for Esc, Tab, arrows and Ctrl+C. Open it over Tailscale.

</td>
<td valign="top">

**Plain-file config**<br>
Settings, shortcuts, machines and detection rules are TOML files you can edit inside the app. Updates install from
Settings.

</td>
</tr>
</table>

### Supported

| Agents | Claude Code · Codex CLI · Gemini CLI · opencode · any shell · your own via TOML rules |
|---|---|
| **Desktop** | Windows 10 / 11 · Linux x64 and arm64 · macOS (from source) |
| **Anywhere else** | Phone browser · remote Linux/macOS servers over SSH |

## Get started

### Windows

1. **[Download Drover](https://github.com/doquangthanh/drover/releases/latest/download/drover.exe)** and save it
   anywhere, such as your Desktop.
2. **Open it.** Drover starts right away. There is no setup wizard and nothing else to install.
3. The first time, Windows may say it doesn't recognise the app. Click **More info**, then **Run anyway**.

### Linux

```sh
curl -fsSL https://raw.githubusercontent.com/doquangthanh/drover/main/scripts/install.sh | sh
```

Installs the latest release (x64 or arm64) into `~/.local/share/drover`, links `dr` and `drover` into
`~/.local/bin` and adds Drover to your app menu. No Python or Node needed. Run the same command again to update, or
use **Settings → Check for updates**. Pin a version with `DROVER_VERSION=v0.1.8`.

### First five minutes

| Step | Do this |
|---|---|
| 1. Start an agent | Click **+** in the tab bar or press **Ctrl+A c**. Pick the agent, a folder, an optional worktree and a first prompt. |
| 2. Walk away | Close the window if you like. The agent keeps going. |
| 3. Answer whoever needs you | Press **Ctrl+A n** to jump to the next agent waiting on you, or open the Inbox. |
| 4. Let agents help each other | Run `dr skill >> AGENTS.md` in your project so your agents know how to use `dr`. |
| 5. Add another machine | `dr machine add vps-1 deploy@vps-1 --install` |

## How it works

```mermaid
flowchart LR
  subgraph You
    W[Drover window]
    P[Phone browser]
    C[dr CLI]
  end
  subgraph PC[Your computer]
    S[(drover-server<br/>127.0.0.1 + token)]
    A1[Claude Code]
    A2[Codex]
    A3[Any shell]
  end
  subgraph VPS[Remote server]
    R[(drover-server)]
    A4[Gemini]
  end
  W -- WebSocket --> S
  P -- Tailscale / SSH tunnel --> S
  C --> S
  S --> A1 & A2 & A3
  S -- SSH tunnel --> R --> A4
```

The server owns every terminal, reads each screen to work out its state and serves the UI. The window, your phone
and the `dr` command are all clients of it, which is why agents survive closing the window.

## Keyboard

The prefix is **Ctrl+A**, tmux style. Press it twice to send a real Ctrl+A to the agent.

| Keys | Action |
|---|---|
| **Ctrl+A c** | New agent |
| **Ctrl+A n** | Next agent that needs you |
| **Ctrl+A /** | Find any agent or text |
| **Ctrl+A %** / **Ctrl+A "** | Split side by side / stacked |
| **Ctrl+A z** / **Ctrl+A x** | Zoom / close pane |
| **Ctrl+A :** / **Ctrl+A ?** | All commands / all shortcuts |

<details>
<summary><b>CLI reference (<code>dr</code>)</b></summary>

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

Exit codes: `2` timeout, `3` not found, `4` refused by policy, `10` server unavailable.
On Windows the same file is the CLI: `drover status`, `drover server autostart on`. Inside agent panes `dr` is on PATH.
`hd`, the old name, still works.

</details>

<details>
<summary><b>Remote machines and phone</b></summary>

`dr machine add vps-1 deploy@vps-1.tail-net --install` installs uv + Drover on a Linux/macOS server (build the wheel
first with `uv build --wheel`), starts its server and connects through an SSH tunnel. The remote server only listens
on 127.0.0.1 and host keys are checked against `known_hosts`.

The UI has a phone layout (up to 760 px wide): bottom tab bar, one full-screen terminal with a key strip and a message
box, file tree and editor, dialogs as bottom sheets. The simplest route is SSH from the phone and `dr attach NAME`.
For the full UI over Tailscale: `dr server stop`, `dr server run --listen <tailscale-ip>`, then open the link from
`dr server url`. Anyone with that link controls your agents, so keep it private.

</details>

<details>
<summary><b>Config and security</b></summary>

Config lives in `%LOCALAPPDATA%\drover` on Windows and `~/.config/drover` on Linux/macOS: `settings.toml`,
`keys.toml`, `machines.toml`, `rules/*.toml`, plus an `AGENTS.md` that explains them so an agent can change Drover for
you. Logs and session state sit next to it (`~/.local/state/drover` on Linux).

- The server binds 127.0.0.1 on a random port with a random token stored in an owner-only file.
- Any program running inside a Drover pane can control all panes through `dr`.
- An agent cannot answer another agent's permission prompt unless you allow it
  (`orchestration.agents_may_answer_permission_prompts`).

</details>

<details>
<summary><b>Build from source</b></summary>

Needs [uv](https://docs.astral.sh/uv/) (Python 3.12) and Node 20.19+ or 22+.

```sh
git clone https://github.com/doquangthanh/drover && cd drover
uv sync
npm --prefix frontend ci
npm --prefix frontend run build      # -> src/drover/web_dist/, served at / (and /ui/)
uv run drover                        # opens the window (starts drover-server if needed)
uv tool install --editable .         # optional: put dr and drover on PATH
```

For UI work run the server, then `npm --prefix frontend run dev`: the dev server proxies `/ws`, `/rpc`, `/static` and
`/health` to the running server (read from `daemon.json`; override with `DROVER_STATE_DIR`).

| Check | Command |
|---|---|
| Python tests | `uv run pytest` |
| Lint | `uv run ruff check src tests` |
| UI types / tests | `npm --prefix frontend run typecheck` · `npm --prefix frontend test` |
| Windows app | `uv run pyinstaller packaging/drover.spec --noconfirm` → `dist\drover.exe` |

Tagging `v*` builds the Windows app and the Linux bundles in CI and attaches them to the GitHub release.

</details>

<details>
<summary><b>Coming from herd?</b></summary>

Drover used to be called herd. On first start Drover moves your old `herd` settings and sessions over and replaces the
old sign-in autostart entry. On Linux, re-run the install command above; it removes the old install. `hd` keeps working
as an alias of `dr`. Remote machines need `dr machine add … --install` once.

</details>

## License

Apache-2.0. Inspired by [Herdr](https://github.com/herdrdev/herdr); detection rules build on Herdr's
`distribution/agent-detection` (Apache-2.0). Terminals by xterm.js (MIT, license in
`src/drover/web/vendor/LICENSE-xterm.txt`).
