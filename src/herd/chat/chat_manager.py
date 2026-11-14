"""All chats of this daemon: create, find, list, remove; restores the saved ones on start."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from herd.chat.chat_session import PERMISSION_MODES, ChatSession
from herd.chat.chat_store import ChatStore


class ChatError(Exception):
    pass


class ChatManager:
    def __init__(self, folder: Path, emit: Callable[[str, Any], None], client_factory: Callable | None = None) -> None:
        self.store = ChatStore(folder)
        self._emit = emit
        self._factory = client_factory
        self.chats: dict[str, ChatSession] = {}
        for meta in self.store.list_meta():
            self.chats[meta["id"]] = self._session(meta)

    def _session(self, meta: dict) -> ChatSession:
        kwargs = {"client_factory": self._factory} if self._factory else {}
        return ChatSession(meta, self.store, lambda op: self._emit("chat", op), self.changed, **kwargs)

    def changed(self) -> None:
        self._emit("chats", self.snapshot())

    def snapshot(self) -> list[dict]:
        return sorted((c.to_public() for c in self.chats.values()), key=lambda c: c["updated_at"])

    def get(self, chat_id: str) -> ChatSession:
        chat = self.chats.get(chat_id)
        if not chat:
            raise ChatError(f"no such chat: {chat_id}")
        return chat

    def create(self, cwd: str, name: str | None = None, model: str | None = None,
               permission_mode: str = "default", space_id: str | None = None) -> ChatSession:
        if not Path(cwd).is_dir():
            raise ChatError(f"not a folder: {cwd}")
        if permission_mode not in PERMISSION_MODES:
            raise ChatError(f"unknown permission mode: {permission_mode}")
        number = 1 + max((int(c[1:]) for c in self.chats if c[1:].isdigit()), default=0)
        now = time.time()
        meta = {"id": f"c{number}", "name": (name or Path(cwd).name or "chat")[:60], "cwd": str(Path(cwd).resolve()),
                "space_id": space_id, "model": model, "permission_mode": permission_mode, "session_id": None,
                "created_at": now, "updated_at": now}
        self.store.save_meta(meta)
        chat = self._session(meta)
        self.chats[meta["id"]] = chat
        self.changed()
        return chat

    def rename(self, chat_id: str, name: str) -> None:
        chat = self.get(chat_id)
        chat.meta["name"] = name[:60]
        self.store.save_meta(chat.meta)
        self.changed()

    async def remove(self, chat_id: str) -> None:
        chat = self.get(chat_id)
        await chat.close()
        self.chats.pop(chat_id, None)
        self.store.delete(chat_id)
        self.changed()

    async def shutdown(self) -> None:
        for chat in list(self.chats.values()):
            await chat.close()
