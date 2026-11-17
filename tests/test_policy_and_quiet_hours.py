"""Orchestration policy limits, permission-answer rules, and quiet-hours windows."""

from __future__ import annotations

import datetime as dt

import pytest

from drover.core.orchestration_policy import OrchestrationPolicy, PolicyError
from drover.notify.desktop_notifier_service import in_quiet_hours


def test_defaults_when_settings_section_is_empty():
    policy = OrchestrationPolicy.from_settings({})
    assert (policy.max_panes, policy.max_depth, policy.answer_prompts) == (0, 3, "ask-user")


def test_no_pane_limit_by_default_but_depth_stays_capped():
    policy = OrchestrationPolicy.from_settings({})
    policy.check_spawn(500, None)  # 0 = no limit on live panes, like Herdr
    with pytest.raises(PolicyError, match="nest"):
        policy.check_spawn(500, 3)


def test_from_settings_reads_and_coerces_values():
    policy = OrchestrationPolicy.from_settings(
        {"max_panes": "4", "max_depth": 1, "agents_may_answer_permission_prompts": "never"})
    assert (policy.max_panes, policy.max_depth, policy.answer_prompts) == (4, 1, "never")


def test_pane_limit_refuses_spawn_at_capacity():
    policy = OrchestrationPolicy(max_panes=2)
    policy.check_spawn(1, None)
    with pytest.raises(PolicyError, match="pane limit"):
        policy.check_spawn(2, None)


def test_depth_limit_counts_the_new_child():
    policy = OrchestrationPolicy(max_depth=3)
    policy.check_spawn(0, 2)  # child lands at depth 3: allowed
    with pytest.raises(PolicyError, match="nest 3 levels"):
        policy.check_spawn(0, 3)


def test_agent_cannot_answer_blocked_pane_unless_always():
    assert OrchestrationPolicy(answer_prompts="ask-user").may_agent_answer("blocked") is False
    assert OrchestrationPolicy(answer_prompts="never").may_agent_answer("blocked") is False
    assert OrchestrationPolicy(answer_prompts="always").may_agent_answer("blocked") is True


def test_agent_may_type_into_non_blocked_pane():
    assert OrchestrationPolicy(answer_prompts="never").may_agent_answer("working") is True


@pytest.mark.parametrize("spec", ["", "23:00", "nonsense", "25:00-07:00"])
def test_empty_or_malformed_spec_is_never_quiet(spec):
    assert in_quiet_hours(spec, dt.time(3, 0)) is False


def test_same_day_window_bounds():
    spec = "09:00-17:00"
    assert in_quiet_hours(spec, dt.time(12, 0))
    assert not in_quiet_hours(spec, dt.time(8, 59))
    assert in_quiet_hours(spec, dt.time(9, 0))  # start inclusive
    assert not in_quiet_hours(spec, dt.time(17, 0))  # end exclusive


def test_window_wrapping_midnight():
    spec = "23:00-07:00"
    assert in_quiet_hours(spec, dt.time(23, 30))
    assert in_quiet_hours(spec, dt.time(0, 15))
    assert in_quiet_hours(spec, dt.time(6, 59))
    assert not in_quiet_hours(spec, dt.time(7, 0))
    assert not in_quiet_hours(spec, dt.time(12, 0))
    assert not in_quiet_hours(spec, dt.time(22, 59))


def test_whitespace_around_separator_is_tolerated():
    assert in_quiet_hours(" 22:00 - 07:00 ", dt.time(1, 0))
