# Phase 02 — Daemon serving, cache headers, packaging

## Context Links
- `src/herd/daemon/web_server.py` (`build_app`, `SECURITY_HEADERS` has `Cache-Control: no-store`, `add_static("/static/", ...)`)
- `src/herd/app_paths.py::web_static_dir`
- `packaging/herd.spec` (`collect_data_files("herd", includes=["web/**/*", ...])`)
- `pyproject.toml` (hatch wheel `packages = ["src/herd"]`)
- `tests/daemon_harness.py` (calls `build_app(ctx)`)
- `src/herd/desktop/desktop_window_launcher.py` (uses `web_static_dir()/app-icon.ico`)

## Overview
Priority P1. Status completed. Daemon serves new UI at `/ui/` alongside legacy `/`, with correct caching; packaging includes the build.

## Key Insights
- aiohttp `add_static` raises `ValueError` if dir missing -> fresh checkouts/CI without `npm run build` would break `build_app` and all 238 tests. Must guard.
- Hatch skips gitignored files unless listed in `artifacts`.
- `web_static_dir()` keeps meaning "shared static assets" (icons, ace, favicon) -> desktop launcher untouched.

## Requirements
- `GET /ui/` and `/ui/index.html` -> `web_dist/index.html`, `no-store` + security headers. If not built -> 503 text "UI not built: cd frontend && npm run build".
- `GET /ui/assets/*` -> `Cache-Control: public, max-age=31536000, immutable`.
- `/static/*` unchanged (legacy UI must keep working).
- Packaging: spec includes `web_dist/**/*`; wheel includes it via hatch artifacts.

## Architecture
- `app_paths.web_dist_dir() -> Path(__file__).parent / "web_dist"`.
- `web_server.py`: `ui_index` handler; `add_static("/ui/assets/", dist/"assets")` only when it exists; one `@web.middleware` (or `on_response_prepare`) that sets immutable cache for paths starting `/ui/assets/`. Keep file <200 lines; if it grows, extract `web_ui_routes.py` (`add_ui_routes(app)`).

## Related Code Files
- Modify: `src/herd/app_paths.py`, `src/herd/daemon/web_server.py`, `packaging/herd.spec`, `pyproject.toml`
- Create: `src/herd/daemon/web_ui_routes.py` (if needed for size), `tests/test_web_ui_static_serving.py`

## Implementation Steps
1. Add `web_dist_dir()`.
2. Add UI routes + cache middleware with missing-dist guard.
3. herd.spec: `includes=["web/**/*", "web_dist/**/*", "status/rules/*.toml"]`; add comment "run `npm --prefix frontend ci && npm --prefix frontend run build` first"; optionally fail spec early if `web_dist/index.html` missing.
4. pyproject: `[tool.hatch.build] artifacts = ["src/herd/web_dist/**"]`.
5. Tests (aiohttp test client via existing harness patterns): missing dist -> 503 and app still builds; with temp dist (monkeypatch `web_dist_dir`) -> index no-store, asset immutable, `/ui/../` traversal rejected (aiohttp static already normalises; assert 403/404).
6. Run full pytest.

## Todo List
- [x] web_dist_dir
- [x] /ui routes + cache middleware + guard
- [x] herd.spec + pyproject artifacts
- [x] tests; full suite green

## Success Criteria
- 238 existing + new tests pass with and without a build present.
- Browser `http://127.0.0.1:PORT/ui/?token=...` loads the placeholder; reload shows assets from cache.

## Risk Assessment
- Middleware overriding security headers on index -> set cache only on `/ui/assets/`.
- Packaged build missing web_dist -> spec early-fail check.

## Security Considerations
- Index stays harmless (token required for /ws, /rpc). No directory listing (`show_index=False`). Token never embedded in HTML.

## Next Steps
Phase 03 core modules.
