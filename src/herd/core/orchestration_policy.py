"""Limits on agents spawning agents, and who may answer permission prompts."""

from __future__ import annotations

from dataclasses import dataclass


class PolicyError(Exception):
    """Raised when an action is refused by the orchestration policy."""


@dataclass
class OrchestrationPolicy:
    max_panes: int = 12
    max_depth: int = 3
    answer_prompts: str = "ask-user"  # never | ask-user | always

    @staticmethod
    def from_settings(section: dict) -> OrchestrationPolicy:
        return OrchestrationPolicy(
            max_panes=int(section.get("max_panes", 12)),
            max_depth=int(section.get("max_depth", 3)),
            answer_prompts=str(section.get("agents_may_answer_permission_prompts", "ask-user")),
        )

    def check_spawn(self, live_panes: int, parent_depth: int | None) -> None:
        if live_panes >= self.max_panes:
            raise PolicyError(f"pane limit reached ({self.max_panes}); close something or raise max_panes")
        if parent_depth is not None and parent_depth + 1 > self.max_depth:
            raise PolicyError(f"agents may only nest {self.max_depth} levels deep")

    def may_agent_answer(self, target_state: str) -> bool:
        """An agent (not the user) is typing into a pane that is waiting on a permission prompt."""
        if target_state != "blocked":
            return True
        return self.answer_prompts == "always"
