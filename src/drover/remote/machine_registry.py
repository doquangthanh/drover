"""machines.toml: remote machines reached over SSH."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from drover.app_paths import config_dir
from drover.config.settings_loader import read_toml

ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
RESERVED = {"local", "self", "this"}


@dataclass
class Machine:
    alias: str
    target: str  # user@host or ~/.ssh/config Host
    port: int = 22
    key: str = ""  # optional identity file; empty = ssh-agent / default keys
    known_hosts: bool = True  # verify host keys

    @property
    def user_host(self) -> tuple[str | None, str]:
        user, _, host = self.target.rpartition("@")
        return (user or None), host


def machines_file() -> Path:
    return config_dir() / "machines.toml"


def load_machines() -> dict[str, Machine]:
    raw = read_toml(machines_file()).get("machines", {})
    out = {}
    for alias, item in raw.items():
        if not ALIAS_RE.match(alias) or not isinstance(item, dict) or not item.get("target"):
            continue
        out[alias] = Machine(alias=alias, target=str(item["target"]), port=int(item.get("port", 22)),
                             key=str(item.get("key", "")), known_hosts=bool(item.get("known_hosts", True)))
    return out


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def save_machines(machines: dict[str, Machine]) -> None:
    lines = ["# Remote machines for drover. Edit freely; drover reconnects on save.", ""]
    for m in machines.values():
        lines.append(f"[machines.{m.alias}]")
        lines.append(f"target = {_quote(m.target)}")
        if m.port != 22:
            lines.append(f"port = {m.port}")
        if m.key:
            lines.append(f"key = {_quote(m.key)}")
        if not m.known_hosts:
            lines.append("known_hosts = false")
        lines.append("")
    machines_file().write_text("\n".join(lines), encoding="utf-8")


def validate_new(alias: str, target: str, existing: dict[str, Machine]) -> None:
    if not ALIAS_RE.match(alias) or alias in RESERVED:
        raise ValueError("name: lowercase letters, digits, - or _, max 32 chars")
    if re.fullmatch(r"[sta]\d+", alias):
        raise ValueError("name looks like an internal id (s1, t3, a2…); pick another")
    if alias in existing:
        raise ValueError(f"machine '{alias}' already exists")
    if not target or any(ch.isspace() for ch in target) or target.startswith("-"):
        raise ValueError("target must look like user@host")


__all__ = ["Machine", "asdict", "load_machines", "save_machines", "validate_new"]
