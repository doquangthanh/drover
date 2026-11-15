"""One chat: drives a Claude conversation through the Agent SDK and turns what comes back into transcript items.

A turn: `send` -> user item, then a task feeds the SDK's messages through TranscriptBuilder. Permission questions
(`can_use_tool`) become a pending `permission` item and the turn waits for `answer`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from drover.chat.chat_store import ChatStore
from drover.chat.claude_locator import find_claude_exe
from drover.chat.transcript_builder import TranscriptBuilder, new_id

log = logging.getLogger(__name__)

PERMISSION_MODES = ("default", "acceptEdits", "plan", "bypassPermissions")


class ChatBusy(Exception):
    pass


def make_client(options: Any) -> Any:
    from claude_agent_sdk import ClaudeSDKClient

    return ClaudeSDKClient(options=options)


class ChatSession:
    def __init__(self, meta: dict, store: ChatStore, publish: Callable[[dict], None],
                 on_change: Callable[[], None], client_factory: Callable[[Any], Any] = make_client) -> None:
        self.meta = meta
        self.store = store
        self.publish = publish
        self.on_change = on_change
        self._factory = client_factory
        self.builder = TranscriptBuilder(store.load_items(meta["id"]))
        self.state = "idle"  # idle | working | blocked
        self._client: Any = None
        self._task: asyncio.Task | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._connect_lock = asyncio.Lock()
        self._info: dict | None = None  # commands and models the CLI offers, fetched on first use

    @property
    def id(self) -> str:
        return self.meta["id"]

    def items(self) -> list[dict]:
        return list(self.builder.items.values())

    def to_public(self) -> dict:
        m = self.meta
        return {"id": m["id"], "name": m["name"], "cwd": m["cwd"], "space_id": m.get("space_id"), "state": self.state,
                "permission_mode": m["permission_mode"], "model": m.get("model"), "updated_at": m["updated_at"]}

    # ---- output -----------------------------------------------------------------------------------------------
    def _emit(self, ops: list[dict]) -> None:
        for op in ops:
            if op["op"] == "session":
                self.meta.update({k: op[k] for k in ("session_id", "model") if op.get(k)})
                self.store.save_meta(self.meta)
                continue
            if op["op"] == "item" and not op["item"].get("live"):
                self.store.append_item(self.id, op["item"])
            self.publish({"chat": self.id, **op})

    def _set_state(self, state: str) -> None:
        if state != self.state:
            self.state = state
            self.meta["updated_at"] = time.time()
            self.store.save_meta(self.meta)
            self.on_change()

    # ---- input ------------------------------------------------------------------------------------------------
    async def send(self, text: str, images: list[dict]) -> None:
        if self.state != "idle":
            raise ChatBusy("The agent is still working on the previous message.")
        self._emit(self.builder.user(text, images))
        content = [{"type": "image", "source": {"type": "base64", "media_type": i["media_type"], "data": i["data"]}} for i in images]
        if text:
            content.append({"type": "text", "text": text})
        self._set_state("working")
        self._task = asyncio.create_task(self._turn(content))

    async def _prompt(self, content: list[dict]) -> AsyncIterator[dict]:
        yield {"type": "user", "message": {"role": "user", "content": content}, "parent_tool_use_id": None, "session_id": "default"}

    async def _turn(self, content: list[dict]) -> None:
        try:
            await self._ensure_client()
            await self._client.query(self._prompt(content))
            async for msg in self._client.receive_response():
                self._emit(self.builder.feed(msg))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("chat %s failed", self.id)
            self._emit(self.builder.notice(f"The agent stopped: {exc}", "error"))
            await self._drop_client()
        finally:
            self._emit(self.builder.finish_turn())
            self._set_state("idle")

    async def _ensure_client(self) -> None:
        async with self._connect_lock:
            if self._client is None:
                client = self._factory(self._options())
                await client.connect()
                self._client = client

    async def options(self) -> dict:
        """Slash commands and models the CLI offers. Starts the CLI the first time (about a second), then answers from memory."""
        if self._info is None:
            await self._ensure_client()
            info = await self._client.get_server_info() or {}
            self._info = {
                "commands": [{"name": c["name"], "description": c.get("description", ""), "hint": c.get("argumentHint") or ""}
                             for c in info.get("commands", []) if c.get("name")],
                "models": [{"value": m["value"], "label": m.get("displayName") or m["value"], "description": m.get("description", "")}
                           for m in info.get("models", []) if m.get("value")],
            }
        return self._info

    async def set_model(self, model: str) -> None:
        """`default` (or empty) means the CLI's own choice."""
        value = None if model in ("", "default") else model
        self.meta["model"] = value
        self.store.save_meta(self.meta)
        if self._client is not None:
            await self._client.set_model(value)
        self.on_change()

    def _options(self) -> Any:
        from claude_agent_sdk import ClaudeAgentOptions

        return ClaudeAgentOptions(cwd=self.meta["cwd"], include_partial_messages=True, can_use_tool=self._can_use_tool,
                                  permission_mode=self.meta["permission_mode"], model=self.meta.get("model") or None,
                                  resume=self.meta.get("session_id") or None, cli_path=find_claude_exe())

    # ---- permissions --------------------------------------------------------------------------------------------
    async def _can_use_tool(self, name: str, tool_input: dict, context: Any) -> Any:
        from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

        item = {"id": new_id(), "kind": "permission", "tool": name, "input": tool_input, "status": "pending",
                "title": getattr(context, "title", None), "detail": getattr(context, "description", None)}
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[item["id"]] = future
        self._emit(self.builder.put(item))
        self._set_state("blocked")
        try:
            allow, always = await future
        finally:
            self._pending.pop(item["id"], None)
        item["status"] = "allowed" if allow else "denied"
        self._emit(self.builder.put(item))
        self._set_state("working")
        if not allow:
            return PermissionResultDeny(message="The user denied this action.")
        suggestions = list(getattr(context, "suggestions", None) or [])
        return PermissionResultAllow(updated_permissions=suggestions) if always and suggestions else PermissionResultAllow()

    def answer(self, request: str, allow: bool, always: bool = False) -> bool:
        future = self._pending.get(request)
        if not future or future.done():
            return False
        future.set_result((allow, always))
        return True

    # ---- control ------------------------------------------------------------------------------------------------
    async def interrupt(self) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_result((False, False))
        if self._client is not None and self.state != "idle":
            await self._client.interrupt()

    async def set_permission_mode(self, mode: str) -> None:
        self.meta["permission_mode"] = mode
        self.store.save_meta(self.meta)
        if self._client is not None:
            await self._client.set_permission_mode(mode)

    async def _drop_client(self) -> None:
        client, self._client, self._info = self._client, None, None
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                log.debug("disconnect failed for chat %s", self.id, exc_info=True)

    async def close(self) -> None:
        for future in self._pending.values():
            if not future.done():
                future.set_result((False, False))
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
        await self._drop_client()
