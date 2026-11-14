"""Chats on disk: one `<id>.json` (settings) and one `<id>.jsonl` (transcript, one item per line, later lines win)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)


class ChatStore:
    def __init__(self, folder: Path) -> None:
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)

    def list_meta(self) -> list[dict]:
        metas = []
        for path in sorted(self.folder.glob("*.json")):
            try:
                metas.append(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError):
                log.warning("skipping unreadable chat file %s", path)
        return metas

    def save_meta(self, meta: dict) -> None:
        path = self.folder / f"{meta['id']}.json"
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(meta), encoding="utf-8")
        tmp.replace(path)

    def append_item(self, chat_id: str, item: dict) -> None:
        with (self.folder / f"{chat_id}.jsonl").open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(item) + "\n")

    def load_items(self, chat_id: str) -> list[dict]:
        path = self.folder / f"{chat_id}.jsonl"
        if not path.exists():
            return []
        items: dict[str, dict] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue  # a half-written last line after a crash
            items[item["id"]] = item
        return list(items.values())

    def delete(self, chat_id: str) -> None:
        for suffix in (".json", ".jsonl"):
            (self.folder / f"{chat_id}{suffix}").unlink(missing_ok=True)
