"""Pure rules for the "restore stopped panes" dialog (port of the web UI's `unaskedStopped`)."""

from __future__ import annotations


def local_only(stopped: list[dict]) -> list[dict]:
    """Remote machine panes (ids like `alias:%3`) need a machine UI the TUI does not have yet."""
    return [s for s in stopped if ":" not in s["id"]]


def unasked_stopped(stopped: list[dict], asked: set[str]) -> list[dict]:
    return [s for s in local_only(stopped) if s["id"] not in asked]
