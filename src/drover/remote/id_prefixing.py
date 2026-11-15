"""Translate ids between a remote daemon ("%3") and the hub's combined view ("vps-1:%3")."""

from __future__ import annotations

from typing import Any

ID_KEYS = {"id", "space_id", "tab_id", "parent", "focused", "pane", "target", "source", "split_from"}


def prefix_ids(value: Any, alias: str, key: str | None = None) -> Any:
    if isinstance(value, dict):
        return {k: prefix_ids(v, alias, k) for k, v in value.items()}
    if isinstance(value, list):
        return [prefix_ids(v, alias, key) for v in value]
    if isinstance(value, str) and key in ID_KEYS and value and ":" not in value:
        return f"{alias}:{value}"
    return value


STRIP_KEYS = ID_KEYS | {"panes", "tab", "space"}


def strip_ids(value: Any, alias: str, key: str | None = None) -> Any:
    """Remove `alias:` only from id-carrying fields — never from user text like a prompt.

    Layout trees need no special case: their leaves are {"pane": id}.
    """
    marker = f"{alias}:"
    if isinstance(value, dict):
        return {k: strip_ids(v, alias, k) for k, v in value.items() if k != "machine"}
    if isinstance(value, list):
        return [strip_ids(v, alias, key) for v in value]
    if isinstance(value, str) and key in STRIP_KEYS and value.startswith(marker):
        return value[len(marker):]
    return value


def tag_machine(snapshot: dict, alias: str) -> dict:
    for pane in snapshot.get("panes", []):
        pane["machine"] = alias
    for space in snapshot.get("spaces", []):
        space["machine"] = alias
    for stopped in snapshot.get("stopped", []):
        stopped["machine"] = alias
    return snapshot
