"""Load agent detection rules: bundled TOML files, overridden by same-id user files."""

from __future__ import annotations

import logging
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

VALID_STATES = {"working", "blocked", "idle"}
_REGION_RE = re.compile(r"^(title|screen|bottom\((\d+)\))$")


@dataclass
class DetectionRule:
    id: str
    state: str
    priority: int
    region: str
    patterns: list[re.Pattern]


@dataclass
class AgentRuleSet:
    id: str
    aliases: list[str] = field(default_factory=list)
    resume: str = ""
    detect_title: re.Pattern | None = None
    rules: list[DetectionRule] = field(default_factory=list)
    source: str = "bundled"
    path: str = ""

    def names(self) -> set[str]:
        return {self.id, *self.aliases}


def parse_rule_file(path: Path, source: str) -> AgentRuleSet:
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    agent_id = str(raw.get("id") or path.stem)
    rules: list[DetectionRule] = []
    for index, item in enumerate(raw.get("rules", [])):
        state = item.get("state", "")
        region = item.get("region", "screen")
        if state not in VALID_STATES:
            raise ValueError(f"{path.name} rule #{index}: bad state {state!r}")
        if not _REGION_RE.match(region):
            raise ValueError(f"{path.name} rule #{index}: bad region {region!r}")
        regexes = item.get("regex", [])
        if isinstance(regexes, str):
            regexes = [regexes]
        rules.append(
            DetectionRule(
                id=str(item.get("id", f"rule{index}")),
                state=state,
                priority=int(item.get("priority", 0)),
                region=region,
                patterns=[re.compile(p, re.MULTILINE) for p in regexes],
            )
        )
    rules.sort(key=lambda r: r.priority, reverse=True)
    title = raw.get("detect_title")
    return AgentRuleSet(
        id=agent_id,
        aliases=list(raw.get("aliases", [])),
        resume=str(raw.get("resume", "")),
        detect_title=re.compile(title) if title else None,
        rules=rules,
        source=source,
        path=str(path),
    )


def load_rule_sets(bundled_dir: Path, user_dir: Path | None) -> tuple[dict[str, AgentRuleSet], list[str]]:
    """Return {agent_id: ruleset} and a list of human-readable errors."""
    sets: dict[str, AgentRuleSet] = {}
    errors: list[str] = []
    for source, directory in (("bundled", bundled_dir), ("user", user_dir)):
        if directory is None or not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.toml")):
            try:
                rule_set = parse_rule_file(path, source)
            except (ValueError, tomllib.TOMLDecodeError, re.error, OSError) as exc:
                errors.append(f"{path.name}: {exc}")
                continue
            sets[rule_set.id] = rule_set
    return sets, errors


def match_agent_kind(command: str, sets: dict[str, AgentRuleSet]) -> str:
    """Map a launch command like `C:/.../claude.cmd --continue` to an agent id."""
    from herd.pty.pty_backend_factory import split_command

    try:
        tokens = split_command(command) if command else []
    except ValueError:  # unbalanced quotes
        tokens = command.split()
    if not tokens:
        return "shell"
    first = Path(tokens[0]).stem.lower()
    for rule_set in sets.values():
        if first in {n.lower() for n in rule_set.names()}:
            return rule_set.id
    return "shell"
