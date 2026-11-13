"""RPC methods for the Files view: browse and read files inside a space, and which of them changed."""

from __future__ import annotations

import asyncio

from herd.core import space_files
from herd.git import worktree_service as wt
from herd.rpc.rpc_registry import E_BAD_PARAMS, E_NOT_FOUND, RpcError, need, registry


def _root(ctx, p: dict) -> str:
    space = ctx.manager.spaces.get(need(p, "space"))
    if not space:
        raise RpcError(E_NOT_FOUND, "no such space")
    return space.cwd


async def _files_call(func, *args):
    try:
        return await asyncio.to_thread(func, *args)
    except space_files.FileAccessError as exc:
        raise RpcError(E_BAD_PARAMS, str(exc)) from exc
    except OSError as exc:
        raise RpcError(E_BAD_PARAMS, str(exc)) from exc


@registry.method("files.list", "List a folder inside a space (folders first)", "space, path?")
async def files_list(ctx, p: dict) -> dict:
    return await _files_call(space_files.list_dir, _root(ctx, p), str(p.get("path") or ""))


@registry.method("files.read", "Read a text file inside a space (1 MB max)", "space, path")
async def files_read(ctx, p: dict) -> dict:
    return await _files_call(space_files.read_text, _root(ctx, p), need(p, "path"))


@registry.method("files.write", "Save a text file inside a space (create=true makes a new one)",
                 "space, path, text, base_mtime_us?, create?, force?")
async def files_write(ctx, p: dict) -> dict:
    text = p.get("text")
    if not isinstance(text, str):
        raise RpcError(E_BAD_PARAMS, "text must be a string")
    base = p.get("base_mtime_us")
    return await _files_call(space_files.write_text, _root(ctx, p), need(p, "path"), text,
                             int(base) if base is not None else None, bool(p.get("create")), bool(p.get("force")))


@registry.method("files.status", "Changed files in the space's git repo (M/A/D/R/?)", "space")
async def files_status(ctx, p: dict) -> dict:
    return await wt.status_map(_root(ctx, p))
