//! RPC methods for chat agents (a Claude conversation shown as a chat instead of a terminal). Port of
//! `methods_chat.py`.

use std::sync::Arc;

use serde_json::{Value, json};

use crate::chat::file_search;
use crate::chat::session::{ChatSession, PERMISSION_MODES};
use crate::ctx::Ctx;
use crate::method;
use crate::rpc::{E_NOT_FOUND, MethodSpec, RpcError, RpcResult, bad, need_str, opt_i64, opt_str, truthy};

const IMAGE_TYPES: [&str; 4] = ["image/png", "image/jpeg", "image/gif", "image/webp"];
const MAX_IMAGES: usize = 8;
const MAX_IMAGE_B64: usize = 14_000_000; // about 10 MB of picture
const MAX_IMAGES_B64: usize = 22_000_000; // per message, below the daemon message limit of 24 MB

pub fn methods() -> Vec<MethodSpec> {
    vec![
        method!("chat.create", "Start a chat agent in a folder", "cwd, name?, model?, permission_mode?, space?", create),
        method!("chat.list", "All chats", "", list),
        method!("chat.history", "A chat's transcript so far", "chat", history),
        method!("chat.send", "Send a message (text and/or images) to a chat", "chat, text?, images? [{media_type, data}]", send),
        method!("chat.interrupt", "Stop what the agent is doing", "chat", interrupt),
        method!("chat.answer", "Allow or deny a permission request", "chat, request, allow, always?", answer),
        method!("chat.set_mode", "Change how much the agent may do without asking", "chat, permission_mode", set_mode),
        method!("chat.options", "Slash commands and models this chat's agent offers (starts the agent the first time)", "chat", options),
        method!("chat.files", "Project files matching a query, for the @ picker", "chat, query?, limit?", files),
        method!("chat.set_model", "Switch the model of a chat (default = the agent's own choice)", "chat, model", set_model),
        method!("chat.rename", "Rename a chat", "chat, name", rename),
        method!("chat.remove", "Delete a chat and its history", "chat", remove),
    ]
}

fn chat(ctx: &Ctx, p: &Value) -> Result<Arc<ChatSession>, RpcError> {
    ctx.chats.get(&need_str(p, "chat")?).map_err(|e| RpcError::new(E_NOT_FOUND, e))
}

fn opt(p: &Value, key: &str) -> Option<String> {
    Some(opt_str(p, key)).filter(|s| !s.is_empty())
}

fn images(p: &Value) -> Result<Vec<Value>, RpcError> {
    let list = match &p["images"] {
        Value::Null => return Ok(vec![]),
        Value::Array(a) if a.len() <= MAX_IMAGES => a,
        _ => return Err(bad(format!("at most {MAX_IMAGES} images per message"))),
    };
    let mut total = 0;
    for image in list {
        let (kind, data) = (image["media_type"].as_str().unwrap_or_default(), image["data"].as_str());
        let Some(data) = data.filter(|_| IMAGE_TYPES.contains(&kind)) else {
            return Err(bad("each image needs a media_type (png, jpeg, gif, webp) and base64 data"));
        };
        if data.len() > MAX_IMAGE_B64 {
            return Err(bad("an image is larger than 10 MB"));
        }
        total += data.len();
    }
    if total > MAX_IMAGES_B64 {
        return Err(bad("the pictures together are larger than 16 MB"));
    }
    Ok(list.iter().map(|i| json!({"media_type": i["media_type"], "data": i["data"]})).collect())
}

async fn create(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let mode = opt(&p, "permission_mode").unwrap_or_else(|| "default".into());
    let chat = ctx.chats.create(&need_str(&p, "cwd")?, opt(&p, "name").as_deref(), opt(&p, "model").as_deref(), &mode,
                                opt(&p, "space").as_deref()).map_err(bad)?;
    Ok(chat.to_public())
}

async fn list(ctx: Arc<Ctx>, _p: Value) -> RpcResult {
    Ok(ctx.chats.snapshot())
}

async fn history(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let chat = chat(&ctx, &p)?;
    Ok(json!({"chat": chat.to_public(), "items": chat.items()}))
}

async fn send(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let chat = chat(&ctx, &p)?;
    let text = opt_str(&p, "text").trim().to_string();
    let images = images(&p)?;
    if text.is_empty() && images.is_empty() {
        return Err(bad("nothing to send"));
    }
    chat.send(&text, &images).map_err(bad)?;
    Ok(Value::Null)
}

async fn interrupt(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    chat(&ctx, &p)?.interrupt().await.map_err(bad)?;
    Ok(Value::Null)
}

async fn answer(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let chat = chat(&ctx, &p)?;
    Ok(json!({"ok": chat.answer(&need_str(&p, "request")?, truthy(&p, "allow"), truthy(&p, "always"))}))
}

async fn set_mode(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let mode = need_str(&p, "permission_mode")?;
    if !PERMISSION_MODES.contains(&mode.as_str()) {
        return Err(bad(format!("permission_mode must be one of {}", PERMISSION_MODES.join(", "))));
    }
    chat(&ctx, &p)?.set_permission_mode(&mode).await.map_err(bad)?;
    ctx.chats.changed();
    Ok(Value::Null)
}

async fn options(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    chat(&ctx, &p)?.options().await.map_err(|e| bad(format!("could not load the agent's options: {e}")))
}

async fn files(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    let root = chat(&ctx, &p)?.cwd();
    let limit = opt_i64(&p, "limit", 30)?.clamp(1, 100) as usize;
    let limit = if p["limit"].as_i64() == Some(0) { 30 } else { limit }; // Python: `int(p.get("limit") or 30)`
    let query = opt_str(&p, "query");
    let found = tokio::task::spawn_blocking(move || file_search::rank_files(&file_search::list_files(&root), &query, limit))
        .await.map_err(|e| bad(e.to_string()))?;
    Ok(json!({"files": found}))
}

async fn set_model(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    chat(&ctx, &p)?.set_model(&opt_str(&p, "model")).await.map_err(bad)?;
    Ok(Value::Null)
}

async fn rename(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    chat(&ctx, &p)?;
    ctx.chats.rename(&need_str(&p, "chat")?, &need_str(&p, "name")?).map_err(|e| RpcError::new(E_NOT_FOUND, e))?;
    Ok(Value::Null)
}

async fn remove(ctx: Arc<Ctx>, p: Value) -> RpcResult {
    chat(&ctx, &p)?;
    ctx.chats.remove(&need_str(&p, "chat")?).await.map_err(|e| RpcError::new(E_NOT_FOUND, e))?;
    Ok(Value::Null)
}
