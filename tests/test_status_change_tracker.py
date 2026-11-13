"""StatusTracker: debounce, done/acknowledge rules, OSC 7501 reports, terminal states."""

from __future__ import annotations

import time

from herd.status.status_change_tracker import DEBOUNCE_SECONDS, StatusTracker

T0 = 1_000.0


def commit(tracker: StatusTracker, detected, start: float, *, focused: bool = False,
           allow_done: bool = True, last_output: float = 0.0):
    """First observation only sets the candidate; the second one after the debounce commits it."""
    tracker.observe(detected, last_output, focused, start, allow_done)
    return tracker.observe(detected, last_output, focused, start + DEBOUNCE_SECONDS + 0.1, allow_done)


def test_first_detection_only_sets_candidate():
    tracker = StatusTracker(state="idle", since=T0)
    assert tracker.observe("working", 0.0, False, T0) is None
    assert tracker.state == "idle"


def test_change_commits_only_after_debounce():
    tracker = StatusTracker(state="idle", since=T0)
    assert tracker.observe("working", 0.0, False, T0) is None
    assert tracker.observe("working", 0.0, False, T0 + DEBOUNCE_SECONDS - 0.1) is None
    assert tracker.observe("working", 0.0, False, T0 + DEBOUNCE_SECONDS + 0.01) == "working"
    assert tracker.state == "working"


def test_flapping_detection_never_commits():
    tracker = StatusTracker(state="idle", since=T0)
    for i in range(20):
        detected = "working" if i % 2 else "blocked"
        assert tracker.observe(detected, 0.0, False, T0 + i * 0.1) is None
    assert tracker.state == "idle"


def test_working_to_idle_while_unfocused_becomes_done():
    tracker = StatusTracker(state="idle", since=T0)
    commit(tracker, "working", T0, focused=True)
    assert commit(tracker, "idle", T0 + 5) == "done"


def test_working_to_idle_while_focused_stays_idle():
    tracker = StatusTracker(state="idle", since=T0)
    commit(tracker, "working", T0, focused=True)
    assert commit(tracker, "idle", T0 + 5, focused=True) == "idle"


def test_allow_done_false_never_yields_done():
    tracker = StatusTracker(state="idle", since=T0)
    commit(tracker, "working", T0, focused=True)
    assert commit(tracker, "idle", T0 + 5, allow_done=False) == "idle"


def test_done_is_sticky_until_acknowledged():
    tracker = StatusTracker(state="idle", since=T0)
    commit(tracker, "working", T0, focused=True)
    commit(tracker, "idle", T0 + 5)
    assert tracker.state == "done"
    assert commit(tracker, "idle", T0 + 10) is None
    assert tracker.state == "done"
    assert tracker.acknowledge() == "idle"
    assert tracker.state == "idle"
    assert tracker.acknowledge() is None


def test_new_work_after_done_goes_back_to_working():
    tracker = StatusTracker(state="idle", since=T0)
    commit(tracker, "working", T0, focused=True)
    commit(tracker, "idle", T0 + 5)
    assert commit(tracker, "working", T0 + 20) == "working"


def test_blocked_detection_wins_immediately_after_debounce():
    tracker = StatusTracker(state="working", since=T0)
    assert commit(tracker, "blocked", T0) == "blocked"


def test_exited_is_terminal():
    tracker = StatusTracker(state="idle", since=T0)
    assert tracker.mark_exited() == "exited"
    assert tracker.observe("working", 0.0, False, T0) is None
    assert commit(tracker, "working", T0 + 10) is None
    assert tracker.state == "exited"


def test_stopped_is_terminal():
    tracker = StatusTracker(state="stopped", since=T0)
    assert commit(tracker, "working", T0) is None
    assert tracker.state == "stopped"


def test_recent_output_without_detection_counts_as_working():
    tracker = StatusTracker(state="idle", since=T0)
    assert commit(tracker, None, T0, last_output=T0) == "working"


def test_silence_without_detection_is_idle_and_done_when_unfocused():
    tracker = StatusTracker(state="idle", since=T0)
    commit(tracker, None, T0, last_output=T0)
    assert commit(tracker, None, T0 + 100, last_output=T0) == "done"


def test_osc_report_is_authoritative_while_fresh():
    tracker = StatusTracker(state="idle", since=time.time())
    now = time.time()
    tracker.report("blocked")
    assert commit(tracker, "idle", now, last_output=0.0) == "blocked"


def test_osc_done_report_maps_to_done_from_working():
    now = time.time()
    tracker = StatusTracker(state="idle", since=now)
    commit(tracker, "working", now, focused=True)
    tracker.report("done")
    assert commit(tracker, None, now + 5, last_output=0.0) == "done"


def test_stale_osc_report_is_ignored():
    now = time.time()
    tracker = StatusTracker(state="idle", since=now)
    tracker.reported, tracker.reported_at = "blocked", now - 60
    assert commit(tracker, None, now, last_output=now - 10) is None
    assert tracker.state == "idle"
