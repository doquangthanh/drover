"""UI serving (/ and /ui/): built and missing web_dist, cache headers, traversal."""

from __future__ import annotations

import pytest
from aiohttp.test_utils import TestClient, TestServer

from drover.daemon import web_ui_routes
from drover.daemon.web_server import build_app


async def _client(monkeypatch, dist) -> TestClient:
    monkeypatch.setattr(web_ui_routes, "web_dist_dir", lambda: dist)
    client = TestClient(TestServer(build_app(None)))  # UI routes never touch ctx
    await client.start_server()
    return client


@pytest.fixture
def built_dist(tmp_path):
    dist = tmp_path / "web_dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>new ui</html>")
    (dist / "assets" / "app-abc123.js").write_text("console.log(1)")
    (tmp_path / "secret.txt").write_text("secret")
    return dist


async def test_missing_dist_returns_503_and_app_builds(monkeypatch, tmp_path):
    client = await _client(monkeypatch, tmp_path / "nope")
    try:
        for path in ("/", "/ui/", "/ui/index.html"):
            resp = await client.get(path)
            assert resp.status == 503
            assert "npm run build" in await resp.text()
        assert (await client.get("/ui/assets/x.js")).status == 404
        assert (await client.get("/health")).status == 200
    finally:
        await client.close()


async def test_index_served_no_store(monkeypatch, built_dist):
    client = await _client(monkeypatch, built_dist)
    try:
        for path in ("/", "/ui/", "/ui/index.html"):
            resp = await client.get(path)
            assert resp.status == 200
            assert "new ui" in await resp.text()
            assert resp.headers["Cache-Control"] == "no-store"
            assert resp.headers["X-Content-Type-Options"] == "nosniff"
    finally:
        await client.close()


async def test_assets_immutable_cache(monkeypatch, built_dist):
    client = await _client(monkeypatch, built_dist)
    try:
        resp = await client.get("/ui/assets/app-abc123.js")
        assert resp.status == 200
        assert resp.headers["Cache-Control"] == "public, max-age=31536000, immutable"
        assert (await client.get("/ui/assets/missing.js")).status == 404
        # shared static files (icons, ace) keep their own headers
        shared = await client.get("/static/favicon.png")
        assert shared.status == 200
        assert "immutable" not in shared.headers.get("Cache-Control", "")
    finally:
        await client.close()


@pytest.mark.parametrize("path", ["/ui/assets/../../secret.txt", "/ui/assets/%2e%2e/%2e%2e/secret.txt",
                                  "/ui/assets/..%2f..%2fsecret.txt", "/ui/assets/"])
async def test_traversal_and_listing_rejected(monkeypatch, built_dist, path):
    client = await _client(monkeypatch, built_dist)
    try:
        resp = await client.get(path)
        assert resp.status in (403, 404)
        assert "secret" not in await resp.text()
    finally:
        await client.close()
