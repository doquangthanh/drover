# Phase 02 — Daemon connection, app shell, `dr tui` command

## Context links
- `src/drover/daemon/ws_client_session.py` (message shapes), `src/drover/daemon/web_server.py` (`/ws`, token check)
- `src/drover/daemon/daemon_client.py` (`ensure_daemon()` returns `{port, token}`) — has uncommitted edits: only import, do not modify
- `src/drover/cli/cli_main.py` (subparsers + lazy imports), `src/drover/cli/cli_attach_terminal.py` (ws URL pattern)
- `tests/daemon_harness.py` (real daemon in test loop)

## Overview
Priority P1. Status pending. One async ws connection object shared by all widgets + an empty App shell started by `dr tui`.

## Key insights
- Server pushes `{"t":"ev","name":"state","data":combined_state}` on connect and on every structure change (verified: `run()`, `_on_event`).
- `status` events carry `{pane, old, new}`; `pane` events carry one `pane.to_dict()` (verified: status_monitor.py, session_manager.py).
- `attach` always sends a full `replay` first, also on re-attach (verified) -> reconnect = re-attach visible panes, no extra logic.
- `resync` event = full state again (BoundedQueue overflow) — treat like `state`.

## Requirements
- `rpc(method, params) -> result` (await future keyed by id; raise on `error`).
- `send_input(pane, data)`, `attach(pane)`, `detach(pane)`.
- Subscribers: `on_state(state)`, `on_status(data)`, `on_pane(pane_dict)`, `on_output(pane, data, is_replay)`.
- Reconnect with backoff (0.5 s -> 5 s) when daemon restarts; re-attach panes after reconnect.
- Takes base URL + token as args (so tests can point at `TestServer`).

## Architecture
```
DaemonConnection(url, token)
  run(): loop { ws_connect -> reader task; on drop: fail pending futures, sleep backoff, retry }
  dispatch: res -> futures[id]; ev -> app.post_message(StateChanged|PaneStatus|PaneChanged); out/replay -> pane views
TuiApp(App)
  on_mount: run_worker(conn.run()); keeps `state` dict (latest snapshot)
```
Output goes straight to the pane view (direct callback, no Textual message per chunk) — hot path, like the web rule "terminal bytes go straight to xterm".

## Related code files
Create:
- `src/drover/tui/daemon_ws_connection.py` (<150 lines)
- `src/drover/tui/tui_app.py` (App, compose, state holder; grows in later phases, split if >200 lines)
- `src/drover/tui/tui_messages.py` (Textual Message classes: StateChanged, PaneStatusChanged)
- `tests/test_tui_daemon_ws_connection.py`
Modify:
- `src/drover/cli/cli_main.py`: add `tui` subparser ("terminal UI in this terminal") + lazy import of `drover.tui.tui_app.main`. Note: `cli_main.py` is 112 lines, OK.

## Implementation steps
1. Write `DaemonConnection` using `aiohttp.ClientSession.ws_connect(f"{base}/ws?token=..&label=dr-tui")`.
2. Id counter + `dict[int, Future]`; timeout 30 s per rpc.
3. Event fan-out via callbacks set by the app (keep it a plain class, no Textual import -> testable without UI).
4. `tui_app.main()`: `ensure_daemon()` -> build URL -> `TuiApp(conn).run()`; Windows: same proactor policy as `cli_attach_terminal.attach`.
5. App shell compose: Header-less; placeholder sidebar + body; footer line with connection status ("connected"/"reconnecting").
6. Wire `dr tui` in cli_main.

## Todo
- [ ] daemon_ws_connection.py
- [ ] tui_messages.py
- [ ] tui_app.py shell + main()
- [ ] `dr tui` subparser
- [ ] tests

## Success criteria (how checked)
- `pytest -q tests/test_tui_daemon_ws_connection.py` (real daemon via `daemon_harness`, real ws):
  - first message yields a state dict with `spaces/tabs/panes/stopped` keys;
  - `rpc("pane.create", {"command": "", "cwd": tmp})` returns a pane id; `attach` yields a `replay` then `out` after `send_input(pane, "echo hi\r")`;
  - closing the server ws -> connection reports "reconnecting" and recovers when a new server is up (or at least fails pending futures cleanly).
- `pytest -q tests/test_cli_parser_and_skill.py` still passes (parser untouched except new subcommand).
- Manual: `dr tui` opens, shows "connected", `q`-less quit via prefix comes in phase 04 — for now Ctrl+Q (Textual default) quits.

## Risks
- Harness runs daemon in the same loop: ws client must use the harness `TestClient` base URL. Mitigation: URL/token injected.
- Event storms (status every frame) -> coalesce: app re-renders sidebar at most every 100 ms.

## Security
Token only in ws query string to 127.0.0.1 (same as `dr attach`); never printed or logged.

## Next steps
Phase 03 consumes `StateChanged` / `PaneStatusChanged`.
