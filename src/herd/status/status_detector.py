"""Evaluate detection rules against a pane's screen text and title."""

from __future__ import annotations

import re
from dataclasses import dataclass

from herd.status.detection_rule_loader import AgentRuleSet

_BOTTOM_RE = re.compile(r"bottom\((\d+)\)")


@dataclass
class RuleEvaluation:
    rule_id: str
    priority: int
    region: str
    state: str
    matched: bool


def region_text(region: str, title: str, lines: list[str]) -> str:
    if region == "title":
        return title
    if region == "screen":
        return "\n".join(lines)
    match = _BOTTOM_RE.fullmatch(region)
    count = int(match.group(1)) if match else 12
    non_empty = [line for line in lines if line.strip()]
    return "\n".join(non_empty[-count:])


def evaluate(rule_set: AgentRuleSet | None, title: str, lines: list[str]) -> tuple[str | None, list[RuleEvaluation]]:
    """Return (winning state or None, per-rule results in priority order)."""
    results: list[RuleEvaluation] = []
    winner: str | None = None
    if rule_set is None:
        return None, results
    for rule in rule_set.rules:
        text = region_text(rule.region, title, lines)
        matched = any(p.search(text) for p in rule.patterns)
        results.append(RuleEvaluation(rule.id, rule.priority, rule.region, rule.state, matched))
        if matched and winner is None:
            winner = rule.state
    return winner, results


def detect_kind_from_title(title: str, sets: dict[str, AgentRuleSet]) -> str | None:
    for rule_set in sets.values():
        if rule_set.detect_title and rule_set.detect_title.search(title or ""):
            return rule_set.id
    return None
