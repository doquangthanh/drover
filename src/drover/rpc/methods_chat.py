"""RPC methods for chat agents (a Claude conversation shown as a chat instead of a terminal)."""

from __future__ import annotations

import asyncio

from drover.chat import file_search
from drover.chat.chat_manager import ChatError
from drover.chat.chat_session import PERMISSION_MODES, ChatBusy
from drover.rpc.rpc_registry import E_BAD_PARAMS, E_NOT_FOUND, RpcError, need, registry

IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
MAX_IMAGES = 8
MAX_IMAGE_B64 = 14_000_000  # about 10 MB of picture
MAX_IMAGES_B64 = 22_000_000  # per message, below the daemon message limit of 24 MB


def _chat(ctx, p: dict):
    try:
        return ctx.chats.get(need(p, "chat"))
    except ChatError as exc:
        raise RpcError(E_NOT_FOUND, str(exc)) from exc


def _images(p: dict) -> list[dict]:
    images = p.get("images") or []
    if not isinstance(images, list) or len(images) > MAX_IMAGES:
        raise RpcError(E_BAD_PARAMS, f"at most {MAX_IMAGES} images per message")
    for image in images:
        if not isinstance(image, dict) or image.get("media_type") not in IMAGE_TYPES or not isinstance(image.get("data"), str):
            raise RpcError(E_BAD_PARAMS, "each image needs a media_type (png, jpeg, gif, webp) and base64 data")
        if len(image["data"]) > MAX_IMAGE_B64:
            raise RpcError(E_BAD_PARAMS, "an image is larger than 10 MB")
    if sum(len(i["data"]) for i in images) > MAX_IMAGES_B64:
        raise RpcError(E_BAD_PARAMS, "the pictures together are larger than 16 MB")
    return [{"media_type": i["media_type"], "data": i["data"]} for i in images]


@registry.method("chat.create", "Start a chat agent in a folder", "cwd, name?, model?, permission_mode?, space?")
async def chat_create(ctx, p: dict) -> dict:
    try:
        chat = ctx.chats.create(need(p, "cwd"), p.get("name"), p.get("model"), p.get("permission_mode") or "default", p.get("space"))
    except ChatError as exc:
        raise RpcError(E_BAD_PARAMS, str(exc)) from exc
    return chat.to_public()


@registry.method("chat.list", "All chats", "")
async def chat_list(ctx, p: dict) -> list:
    return ctx.chats.snapshot()


@registry.method("chat.history", "A chat's transcript so far", "chat")
async def chat_history(ctx, p: dict) -> dict:
    chat = _chat(ctx, p)
    return {"chat": chat.to_public(), "items": chat.items()}


@registry.method("chat.send", "Send a message (text and/or images) to a chat", "chat, text?, images? [{media_type, data}]")
async def chat_send(ctx, p: dict) -> None:
    chat = _chat(ctx, p)
    text = str(p.get("text") or "").strip()
    images = _images(p)
    if not text and not images:
        raise RpcError(E_BAD_PARAMS, "nothing to send")
    try:
        await chat.send(text, images)
    except ChatBusy as exc:
        raise RpcError(E_BAD_PARAMS, str(exc)) from exc


@registry.method("chat.interrupt", "Stop what the agent is doing", "chat")
async def chat_interrupt(ctx, p: dict) -> None:
    await _chat(ctx, p).interrupt()


@registry.method("chat.answer", "Allow or deny a permission request", "chat, request, allow, always?")
async def chat_answer(ctx, p: dict) -> dict:
    return {"ok": _chat(ctx, p).answer(need(p, "request"), bool(p.get("allow")), bool(p.get("always")))}


@registry.method("chat.set_mode", "Change how much the agent may do without asking", "chat, permission_mode")
async def chat_set_mode(ctx, p: dict) -> None:
    mode = need(p, "permission_mode")
    if mode not in PERMISSION_MODES:
        raise RpcError(E_BAD_PARAMS, f"permission_mode must be one of {', '.join(PERMISSION_MODES)}")
    await _chat(ctx, p).set_permission_mode(mode)
    ctx.chats.changed()


@registry.method("chat.options", "Slash commands and models this chat's agent offers (starts the agent the first time)", "chat")
async def chat_options(ctx, p: dict) -> dict:
    try:
        return await _chat(ctx, p).options()
    except Exception as exc:
        raise RpcError(E_BAD_PARAMS, f"could not load the agent's options: {exc}") from exc


@registry.method("chat.files", "Project files matching a query, for the @ picker", "chat, query?, limit?")
async def chat_files(ctx, p: dict) -> dict:
    root = _chat(ctx, p).meta["cwd"]
    limit = max(1, min(int(p.get("limit") or 30), 100))
    files = await asyncio.to_thread(file_search.list_files, root)
    return {"files": file_search.rank_files(files, str(p.get("query") or ""), limit)}


@registry.method("chat.set_model", "Switch the model of a chat (default = the agent's own choice)", "chat, model")
async def chat_set_model(ctx, p: dict) -> None:
    await _chat(ctx, p).set_model(str(p.get("model") or ""))


@registry.method("chat.rename", "Rename a chat", "chat, name")
async def chat_rename(ctx, p: dict) -> None:
    _chat(ctx, p)
    ctx.chats.rename(need(p, "chat"), need(p, "name"))


@registry.method("chat.remove", "Delete a chat and its history", "chat")
async def chat_remove(ctx, p: dict) -> None:
    _chat(ctx, p)
    await ctx.chats.remove(need(p, "chat"))
