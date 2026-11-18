//! Ported from `tests/test_status_change_tracker.py`.

use super::*;

const T0: f64 = 1_000.0;

/// First observation only sets the candidate; the second one after the debounce commits it.
fn commit(t: &mut StatusTracker, detected: Option<&str>, start: f64, focused: bool, allow_done: bool, last_output: f64) -> Option<String> {
    t.observe(detected, last_output, focused, start, allow_done);
    t.observe(detected, last_output, focused, start + DEBOUNCE_SECONDS + 0.1, allow_done)
}

fn c(t: &mut StatusTracker, detected: &str, start: f64) -> Option<String> {
    commit(t, Some(detected), start, false, true, 0.0)
}

fn cf(t: &mut StatusTracker, detected: &str, start: f64) -> Option<String> {
    commit(t, Some(detected), start, true, true, 0.0)
}

fn s(v: &str) -> Option<String> {
    Some(v.to_string())
}

#[test]
fn first_detection_only_sets_candidate() {
    let mut t = StatusTracker::new("idle", T0);
    assert_eq!(t.observe(Some("working"), 0.0, false, T0, true), None);
    assert_eq!(t.state, "idle");
}

#[test]
fn change_commits_only_after_debounce() {
    let mut t = StatusTracker::new("idle", T0);
    assert_eq!(t.observe(Some("working"), 0.0, false, T0, true), None);
    assert_eq!(t.observe(Some("working"), 0.0, false, T0 + DEBOUNCE_SECONDS - 0.1, true), None);
    assert_eq!(t.observe(Some("working"), 0.0, false, T0 + DEBOUNCE_SECONDS + 0.01, true), s("working"));
    assert_eq!(t.state, "working");
}

#[test]
fn flapping_detection_never_commits() {
    let mut t = StatusTracker::new("idle", T0);
    for i in 0..20 {
        let d = if i % 2 == 1 { "working" } else { "blocked" };
        assert_eq!(t.observe(Some(d), 0.0, false, T0 + i as f64 * 0.1, true), None);
    }
    assert_eq!(t.state, "idle");
}

#[test]
fn working_to_idle_while_unfocused_becomes_done() {
    let mut t = StatusTracker::new("idle", T0);
    cf(&mut t, "working", T0);
    assert_eq!(c(&mut t, "idle", T0 + 5.0), s("done"));
}

#[test]
fn working_to_idle_while_focused_stays_idle() {
    let mut t = StatusTracker::new("idle", T0);
    cf(&mut t, "working", T0);
    assert_eq!(cf(&mut t, "idle", T0 + 5.0), s("idle"));
}

#[test]
fn allow_done_false_never_yields_done() {
    let mut t = StatusTracker::new("idle", T0);
    cf(&mut t, "working", T0);
    assert_eq!(commit(&mut t, Some("idle"), T0 + 5.0, false, false, 0.0), s("idle"));
}

#[test]
fn done_is_sticky_until_acknowledged() {
    let mut t = StatusTracker::new("idle", T0);
    cf(&mut t, "working", T0);
    c(&mut t, "idle", T0 + 5.0);
    assert_eq!(t.state, "done");
    assert_eq!(c(&mut t, "idle", T0 + 10.0), None);
    assert_eq!(t.state, "done");
    assert_eq!(t.acknowledge(), s("idle"));
    assert_eq!(t.state, "idle");
    assert_eq!(t.acknowledge(), None);
}

#[test]
fn new_work_after_done_goes_back_to_working() {
    let mut t = StatusTracker::new("idle", T0);
    cf(&mut t, "working", T0);
    c(&mut t, "idle", T0 + 5.0);
    assert_eq!(c(&mut t, "working", T0 + 20.0), s("working"));
}

#[test]
fn blocked_detection_wins_immediately_after_debounce() {
    let mut t = StatusTracker::new("working", T0);
    assert_eq!(c(&mut t, "blocked", T0), s("blocked"));
}

#[test]
fn exited_is_terminal() {
    let mut t = StatusTracker::new("idle", T0);
    assert_eq!(t.mark_exited(), "exited");
    assert_eq!(t.observe(Some("working"), 0.0, false, T0, true), None);
    assert_eq!(c(&mut t, "working", T0 + 10.0), None);
    assert_eq!(t.state, "exited");
}

#[test]
fn stopped_is_terminal() {
    let mut t = StatusTracker::new("stopped", T0);
    assert_eq!(c(&mut t, "working", T0), None);
    assert_eq!(t.state, "stopped");
}

#[test]
fn recent_output_without_detection_counts_as_working() {
    let mut t = StatusTracker::new("idle", T0);
    assert_eq!(commit(&mut t, None, T0, false, true, T0), s("working"));
}

#[test]
fn silence_without_detection_is_idle_and_done_when_unfocused() {
    let mut t = StatusTracker::new("idle", T0);
    commit(&mut t, None, T0, false, true, T0);
    assert_eq!(commit(&mut t, None, T0 + 100.0, false, true, T0), s("done"));
}

#[test]
fn osc_report_is_authoritative_while_fresh() {
    let now = now_secs();
    let mut t = StatusTracker::new("idle", now);
    t.report("blocked");
    assert_eq!(commit(&mut t, Some("idle"), now, false, true, 0.0), s("blocked"));
}

#[test]
fn osc_done_report_maps_to_done_from_working() {
    let now = now_secs();
    let mut t = StatusTracker::new("idle", now);
    commit(&mut t, Some("working"), now, true, true, 0.0);
    t.report("done");
    assert_eq!(commit(&mut t, None, now + 5.0, false, true, 0.0), s("done"));
}

#[test]
fn stale_osc_report_is_ignored() {
    let now = now_secs();
    let mut t = StatusTracker::new("idle", now);
    t.reported = Some("blocked".into());
    t.reported_at = now - 60.0;
    assert_eq!(commit(&mut t, None, now, false, true, now - 10.0), None);
    assert_eq!(t.state, "idle");
}
