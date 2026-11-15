"""Binary split tree for pane layout inside a tab.

Node shapes (plain dicts so they serialise straight to JSON):
  {"pane": "%3"}
  {"split": "row" | "col", "ratio": 0.5, "a": <node>, "b": <node>}
"row" = side by side (split right), "col" = stacked (split down).
"""

from __future__ import annotations

from typing import Any

Node = dict[str, Any]


def leaf(pane_id: str) -> Node:
    return {"pane": pane_id}


def pane_ids(node: Node | None) -> list[str]:
    if not node:
        return []
    if "pane" in node:
        return [node["pane"]]
    return pane_ids(node["a"]) + pane_ids(node["b"])


def insert(node: Node | None, target: str | None, new_pane: str, direction: str = "row") -> Node:
    """Split `target` leaf (or the last leaf if target missing) and place `new_pane` after it."""
    if not node:
        return leaf(new_pane)
    ids = pane_ids(node)
    if target not in ids:
        target = ids[-1]
    return _split_at(node, target, new_pane, direction)


def _split_at(node: Node, target: str, new_pane: str, direction: str) -> Node:
    if "pane" in node:
        if node["pane"] == target:
            return {"split": direction, "ratio": 0.5, "a": node, "b": leaf(new_pane)}
        return node
    return {**node, "a": _split_at(node["a"], target, new_pane, direction),
            "b": _split_at(node["b"], target, new_pane, direction)}


def remove(node: Node | None, pane_id: str) -> Node | None:
    """Remove a leaf; its sibling takes the parent's place."""
    if not node:
        return None
    if "pane" in node:
        return None if node["pane"] == pane_id else node
    a = remove(node["a"], pane_id)
    b = remove(node["b"], pane_id)
    if a is None:
        return b
    if b is None:
        return a
    return {**node, "a": a, "b": b}


def set_ratio(node: Node | None, path: str, ratio: float) -> Node | None:
    """Update the ratio of the split at `path` ("" = root, "a"/"b" steps)."""
    if not node or "pane" in node:
        return node
    if not path:
        return {**node, "ratio": max(0.1, min(0.9, ratio))}
    step, rest = path[0], path[1:]
    return {**node, step: set_ratio(node[step], rest, ratio)}


def is_valid(node: Any) -> bool:
    if not isinstance(node, dict):
        return False
    if "pane" in node:
        return isinstance(node["pane"], str)
    return node.get("split") in ("row", "col") and is_valid(node.get("a")) and is_valid(node.get("b"))
