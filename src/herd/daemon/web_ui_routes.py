"""Routes for the built React UI (src/herd/web_dist): index at / and /ui/, hashed assets under /ui/assets/.

Safe when the build is absent: the page answers 503 with the build command."""

from __future__ import annotations

from aiohttp import web

from herd.app_paths import web_dist_dir

ASSETS_PREFIX = "/ui/assets/"
IMMUTABLE = "public, max-age=31536000, immutable"
NOT_BUILT = "UI not built: cd frontend && npm run build\n"


def add_ui_routes(app: web.Application, headers: dict[str, str]) -> None:
    """`headers` (security + no-store) are applied to index.html; hashed assets get immutable caching."""
    dist = web_dist_dir()

    async def ui_index(request: web.Request) -> web.StreamResponse:
        index = dist / "index.html"
        if not index.is_file():
            return web.Response(status=503, text=NOT_BUILT, headers=headers)
        return web.FileResponse(index, headers=headers)

    async def immutable_assets(request: web.Request, response: web.StreamResponse) -> None:
        if request.path.startswith(ASSETS_PREFIX) and response.status == 200:
            response.headers["Cache-Control"] = IMMUTABLE

    app.router.add_get("/", ui_index)
    app.router.add_get("/ui/", ui_index)
    app.router.add_get("/ui/index.html", ui_index)
    if (dist / "assets").is_dir():
        app.router.add_static(ASSETS_PREFIX, dist / "assets", show_index=False)
        app.on_response_prepare.append(immutable_assets)
