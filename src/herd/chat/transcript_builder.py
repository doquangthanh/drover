"""Claude Agent SDK messages -> transcript items. This file is the contract every agent adapter has to fill.

Items (JSON-friendly dicts, keyed by `id`):
  user        {text, images:[{media_type, data}]}
  text        {text, live}                      assistant prose; `live` while it is still streaming
  thinking    {text, live}
  tool        {name, input, status: running|done|error|stopped, result, is_error, parent?}
  permission  {tool, input, title, detail, status: pending|allowed|denied}      (built by the session)
  result      {ok, ms, cost, turns, error}      end of a turn
  notice      {text, level}
Operations sent to the UI: {"op":"item","item":{...}} (upsert by id) and {"op":"delta","id","text"} (append while live).
"""

from __future__ import annotations

import uuid
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

MAX_RESULT_CHARS = 20_000


def new_id() -> str:
    return uuid.uuid4().hex[:10]


def result_text(content: Any) -> str:
    """A tool result as plain text (blocks are joined, images become a marker), cut to a sane size."""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text = "\n".join(b.get("text", "[image]") if isinstance(b, dict) else str(b) for b in content)
    else:
        text = "" if content is None else str(content)
    return text if len(text) <= MAX_RESULT_CHARS else text[:MAX_RESULT_CHARS] + f"\n… ({len(text) - MAX_RESULT_CHARS} more characters)"


class TranscriptBuilder:
    def __init__(self, items: list[dict] | None = None) -> None:
        self.items: dict[str, dict] = {i["id"]: i for i in items or []}
        self._live: dict[int, str] = {}  # stream block index -> id of the item being streamed

    def put(self, item: dict) -> list[dict]:
        self.items[item["id"]] = item
        return [{"op": "item", "item": item}]

    def user(self, text: str, images: list[dict]) -> list[dict]:
        return self.put({"id": new_id(), "kind": "user", "text": text, "images": images})

    def notice(self, text: str, level: str = "info") -> list[dict]:
        return self.put({"id": new_id(), "kind": "notice", "text": text, "level": level})

    def feed(self, msg: Any) -> list[dict]:
        if isinstance(msg, StreamEvent):
            return self._stream(msg.event)
        if isinstance(msg, AssistantMessage):
            return self._assistant(msg)
        if isinstance(msg, UserMessage):
            return self._tool_results(msg)
        if isinstance(msg, ResultMessage):
            return self._result(msg)
        if isinstance(msg, SystemMessage) and msg.subtype == "init":
            return [{"op": "session", "session_id": msg.data.get("session_id"), "model": msg.data.get("model")}]
        return []

    def finish_turn(self) -> list[dict]:
        """Anything still running when a turn ends was interrupted."""
        ops: list[dict] = []
        for item in self.items.values():
            if item["kind"] == "tool" and item["status"] == "running":
                item["status"] = "stopped"
                ops += [{"op": "item", "item": item}]
            elif item.get("live"):
                item["live"] = False
                ops += [{"op": "item", "item": item}]
        self._live = {}
        return ops

    def _stream(self, ev: dict) -> list[dict]:
        kind = ev.get("type")
        if kind == "message_start":
            self._live = {}
        elif kind == "content_block_start":
            block_type = ev.get("content_block", {}).get("type")
            if block_type in ("text", "thinking"):
                item = {"id": new_id(), "kind": block_type, "text": "", "live": True}
                self._live[ev["index"]] = item["id"]
                return self.put(item)
        elif kind == "content_block_delta":
            item = self.items.get(self._live.get(ev.get("index"), ""))
            delta = ev.get("delta", {})
            text = delta.get("text") or delta.get("thinking") or ""
            if item and text:
                item["text"] += text
                return [{"op": "delta", "id": item["id"], "text": text}]
        return []

    def _take_live(self, kind: str) -> dict | None:
        for index in sorted(self._live):
            item = self.items.get(self._live[index])
            if item and item["kind"] == kind and item.get("live"):
                del self._live[index]
                return item
        return None

    def _assistant(self, msg: AssistantMessage) -> list[dict]:
        ops: list[dict] = []
        parent = msg.parent_tool_use_id
        for block in msg.content:
            if isinstance(block, (TextBlock, ThinkingBlock)):
                kind, text = ("text", block.text) if isinstance(block, TextBlock) else ("thinking", block.thinking)
                item = self._take_live(kind) or {"id": new_id(), "kind": kind}
                item.update(text=text, live=False)
            elif isinstance(block, ToolUseBlock):
                item = {"id": block.id, "kind": "tool", "name": block.name, "input": block.input,
                        "status": "running", "result": None, "is_error": False}
            else:
                continue
            if parent:
                item["parent"] = parent
            ops += self.put(item)
        return ops

    def _tool_results(self, msg: UserMessage) -> list[dict]:
        ops: list[dict] = []
        if not isinstance(msg.content, list):
            return ops
        for block in msg.content:
            tool = self.items.get(block.tool_use_id) if isinstance(block, ToolResultBlock) else None
            if tool:
                tool.update(result=result_text(block.content), is_error=bool(block.is_error),
                            status="error" if block.is_error else "done")
                ops += [{"op": "item", "item": tool}]
        return ops

    def _result(self, msg: ResultMessage) -> list[dict]:
        error = None
        if msg.is_error:
            error = msg.result or "; ".join(msg.errors or []) or "The turn ended with an error."
        return self.put({"id": new_id(), "kind": "result", "ok": not msg.is_error, "ms": msg.duration_ms,
                         "cost": msg.total_cost_usd, "turns": msg.num_turns, "error": error})
