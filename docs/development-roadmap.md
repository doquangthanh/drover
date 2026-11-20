# Development roadmap

| Area | Status |
|---|---|
| Split into drover-core, drover-web, drover-desktop (plan `plans/261120-1700-split-into-three-repos`) | done in code; first tag v0.2.0-dev; installers and release workflows not yet proven by a full release |
| Daemon, CLI (`dr`), remote machines, desktop window | done |
| Web UI: desktop, tablet, phone layouts, themes, editor, git changes | done |
| React/TypeScript frontend migration (plan `plans/261114-1115-react-frontend-migration`, phases 1-9) | done |
| Agent control CLI: `dr prompt --wait`, `dr keys`, `dr wait-output`, alternate-screen reads, `dr rename`, layout commands, shell completion | done |
| Terminal UI client `dr tui` (plan `plans/261116-0943-textual-tui-client`): sidebar, split panes, prefix keys, restore dialog, narrow layout | done (not yet default; chat view, files, search, mouse, scrollback not included) |
| Resume the exact agent session (session id from agent hooks instead of `--continue`) | planned |
| Integrations that install agent hooks so agents report state/session over OSC 7501 | planned |
| Browser access via cloud relay (plan `plans/261114-1101-public-browser-access-via-cloud-relay`) | planned: targets `frontend/src/core/connection.ts` |
| CSP header for the index page (needs hashed inline theme script) | idea |
| Commit or CI-build `web_dist` for `pip install git+...` users without Node | open question |
