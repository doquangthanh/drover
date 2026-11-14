# Development roadmap

| Area | Status |
|---|---|
| Daemon, CLI (`hd`), remote machines, desktop window | done |
| Web UI: desktop, tablet, phone layouts, themes, editor, git changes | done |
| React/TypeScript frontend migration (plan `plans/261114-1115-react-frontend-migration`, phases 1-9) | done |
| Browser access via cloud relay (plan `plans/261114-1101-public-browser-access-via-cloud-relay`) | planned: targets `frontend/src/core/connection.ts` |
| CSP header for the index page (needs hashed inline theme script) | idea |
| Commit or CI-build `web_dist` for `pip install git+...` users without Node | open question |
