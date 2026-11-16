"""Spaces (a folder/repo on a machine) and tabs (a layout of panes)."""

from __future__ import annotations

import itertools
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

_ids = itertools.count(1)


def new_id(prefix: str) -> str:
    return f"{prefix}{next(_ids)}"


def bump_id_counter(existing: list[str]) -> None:
    """After restoring from disk make sure new ids don't collide."""
    global _ids
    numbers = [int("".join(ch for ch in i if ch.isdigit()) or 0) for i in existing]
    _ids = itertools.count(max(numbers, default=0) + 1)


@dataclass
class Space:
    id: str
    name: str
    cwd: str
    color: int = 0
    custom_name: bool = False  # renamed by hand: stop naming it after the folder its first pane is in

    @staticmethod
    def for_folder(cwd: str, color: int) -> Space:
        name = Path(cwd).name or cwd
        return Space(id=new_id("s"), name=name, cwd=cwd, color=color)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Tab:
    id: str
    space_id: str
    name: str
    layout: dict | None = None
    focused: str | None = None
    zoomed: bool = False
    extra: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
