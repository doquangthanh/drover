//! HTTP + WebSocket front door: the UI, the websocket session and JSON-RPC for the CLI. Port of `web_server.py` and
//! `web_ui_routes.py`. Every data channel needs the daemon token.

use std::path::{Component, Path, PathBuf};
use std::sync::Arc;

use axum::Router;
use axum::body::{Body, Bytes};
use axum::extract::{DefaultBodyLimit, Query, State, WebSocketUpgrade};
use axum::http::{HeaderMap, HeaderValue, StatusCode, Uri, header};
use axum::response::{IntoResponse, Response};
use axum::routing::{get, post};
use serde_json::{Value, json};

use crate::ctx::Ctx;

/// Large enough for a chat message carrying pictures; everything needs the token anyway.
pub const MAX_MESSAGE_BYTES: usize = 24 * 1024 * 1024;
const IMMUTABLE: &str = "public, max-age=31536000, immutable";
const NOT_BUILT: &str = "UI not installed: unpack a drover-web release into DROVER_WEB_DIR\n";

/// Constant-time token check (no early exit on the first differing byte).
pub fn token_ok(ctx: &Ctx, supplied: Option<&str>) -> bool {
    let Some(s) = supplied.filter(|s| !s.is_empty()) else { return false };
    let (a, b) = (s.as_bytes(), ctx.token.as_bytes());
    a.len() == b.len() && a.iter().zip(b).fold(0u8, |acc, (x, y)| acc | (x ^ y)) == 0
}

pub fn router(ctx: Arc<Ctx>) -> Router {
    Router::new()
        .route("/ws", get(ws_handler))
        .route("/rpc", post(rpc_handler))
        .route("/health", get(|| async { axum::Json(json!({"ok": true, "app": "drover"})) }))
        .route("/", get(ui_index))
        .route("/ui/", get(ui_index))
        .route("/ui/index.html", get(ui_index))
        .route("/static/{*path}", get(static_file))
        .route("/ui/assets/{*path}", get(ui_asset))
        .layer(DefaultBodyLimit::max(MAX_MESSAGE_BYTES))
        .with_state(ctx)
}

fn unauthorized() -> Response {
    (StatusCode::UNAUTHORIZED, "bad token").into_response()
}

async fn ws_handler(State(ctx): State<Arc<Ctx>>, Query(q): Query<Vec<(String, String)>>, ws: WebSocketUpgrade) -> Response {
    let get = |k: &str| q.iter().find(|(key, _)| key == k).map(|(_, v)| v.as_str());
    if !token_ok(&ctx, get("token")) {
        return unauthorized();
    }
    let label: String = get("label").unwrap_or("browser").chars().take(40).collect();
    ws.max_message_size(MAX_MESSAGE_BYTES).on_upgrade(move |socket| crate::ws_session::run(ctx, socket, label))
}

async fn rpc_handler(State(ctx): State<Arc<Ctx>>, headers: HeaderMap, body: Bytes) -> Response {
    let auth = headers.get(header::AUTHORIZATION).and_then(|v| v.to_str().ok()).unwrap_or("");
    if !token_ok(&ctx, Some(auth.strip_prefix("Bearer ").unwrap_or(auth).trim())) {
        return unauthorized();
    }
    let bad = |msg: &str| (StatusCode::BAD_REQUEST, axum::Json(json!({"error": {"code": 5, "message": msg}}))).into_response();
    let Ok(body) = serde_json::from_slice::<Value>(&body) else { return bad("invalid JSON") };
    let params = body.get("params").cloned().filter(|p| !p.is_null()).unwrap_or(json!({}));
    if !body.is_object() || !params.is_object() {
        return bad("expected {method, params}");
    }
    let method = match body.get("method") {
        Some(Value::String(s)) => s.clone(),
        None | Some(Value::Null) => "None".into(),
        Some(other) => other.to_string(),
    };
    let result = match ctx.remotes.call_remote(&method, &params).await {
        Some(remote) => remote,
        None => crate::methods::call(ctx, &method, params).await,
    };
    let reply = match result {
        Ok(result) => json!({"result": result}),
        Err(e) => json!({"error": e.to_json()}),
    };
    axum::Json(reply).into_response()
}

fn with_security_headers(mut resp: Response) -> Response {
    let h = resp.headers_mut();
    h.insert("X-Content-Type-Options", HeaderValue::from_static("nosniff"));
    h.insert("Referrer-Policy", HeaderValue::from_static("no-referrer"));
    h.insert(header::CACHE_CONTROL, HeaderValue::from_static("no-store"));
    resp
}

async fn ui_index() -> Response {
    let index = crate::paths::web_root().join("web_dist/index.html");
    let resp = match tokio::fs::read(&index).await {
        Ok(bytes) => ([(header::CONTENT_TYPE, "text/html; charset=utf-8")], bytes).into_response(),
        Err(_) => (StatusCode::SERVICE_UNAVAILABLE, NOT_BUILT).into_response(),
    };
    with_security_headers(resp)
}

/// `rel` under `base`, refusing `..`, absolute paths and drive prefixes.
fn safe_join(base: &Path, rel: &str) -> Option<PathBuf> {
    let rel = Path::new(rel);
    rel.components().all(|c| matches!(c, Component::Normal(_))).then(|| base.join(rel))
}

async fn serve_file(base: PathBuf, rel: &str, cache: Option<&'static str>) -> Response {
    let Some(path) = safe_join(&base, rel) else { return StatusCode::FORBIDDEN.into_response() };
    match tokio::fs::read(&path).await {
        Ok(bytes) => {
            let mime = mime_guess::from_path(&path).first_or_octet_stream();
            let mut resp = Response::new(Body::from(bytes));
            if let Ok(v) = HeaderValue::from_str(mime.as_ref()) {
                resp.headers_mut().insert(header::CONTENT_TYPE, v);
            }
            if let Some(c) = cache {
                resp.headers_mut().insert(header::CACHE_CONTROL, HeaderValue::from_static(c));
            }
            resp
        }
        Err(_) => StatusCode::NOT_FOUND.into_response(),
    }
}

async fn static_file(uri: Uri) -> Response {
    let rel = uri.path().trim_start_matches("/static/").to_string();
    serve_file(crate::paths::web_root().join("web"), &percent_decode(&rel), None).await
}

async fn ui_asset(uri: Uri) -> Response {
    let rel = uri.path().trim_start_matches("/ui/assets/").to_string();
    serve_file(crate::paths::web_root().join("web_dist/assets"), &percent_decode(&rel), Some(IMMUTABLE)).await
}

fn percent_decode(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%'
            && let Some(v) = s.get(i + 1..i + 3).and_then(|h| u8::from_str_radix(h, 16).ok())
        {
            out.push(v);
            i += 3;
            continue;
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn safe_join_refuses_traversal() {
        let base = Path::new("/srv");
        assert_eq!(safe_join(base, "icons/a.svg"), Some(PathBuf::from("/srv/icons/a.svg")));
        assert_eq!(safe_join(base, "../etc/passwd"), None);
        assert_eq!(safe_join(base, "/etc/passwd"), None);
        assert_eq!(percent_decode("%2e%2e/x"), "../x");
    }
}
