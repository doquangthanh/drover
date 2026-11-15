"""Desktop notification wording and urgency per agent state."""

from __future__ import annotations

import pytest

from drover.notify.desktop_notifier_service import MESSAGES, URGENCY, build_message


def test_blocked_message_names_the_agent_and_adds_context():
    title, body = build_message("api", "claude", "blocked", "  Edit   src/app.py  ")
    assert title == "api needs you"
    assert body.splitlines()[0] == "Claude Code is waiting for your answer or approval."
    assert body.splitlines()[1] == "Edit src/app.py"


def test_unknown_kind_falls_back_to_its_own_name_and_no_detail_line():
    title, body = build_message("x", "mytool", "done")
    assert title == "x finished"
    assert body.startswith("mytool finished") and "\n" not in body


def test_detail_is_truncated():
    _, body = build_message("x", "codex", "exited", "a" * 500)
    assert len(body.splitlines()[1]) == 140


@pytest.mark.parametrize("state", list(MESSAGES))
def test_every_notifying_state_has_an_urgency(state):
    assert URGENCY[state] in {"Critical", "Normal", "Low"}
    assert build_message("n", "", state)[0]
