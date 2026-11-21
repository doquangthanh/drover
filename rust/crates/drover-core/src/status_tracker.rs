//! Turn noisy per-frame detections into stable pane states with debounce.
//!
//! Public states: working | blocked | idle | done | exited | stopped.
//! `done` = a working -> idle transition, kept until the user looks at the pane.
//! Port of `drover/status/status_change_tracker.py`. Times are Unix seconds (f64), passed in for testability.

pub const DEBOUNCE_SECONDS: f64 = 0.5;
/// Generic fallback: output within this window = working.
pub const ACTIVITY_WINDOW: f64 = 1.5;
/// An OSC 7501 report stays authoritative this long.
const REPORT_FRESH_SECONDS: f64 = 30.0;

pub fn now_secs() -> f64 {
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs_f64()).unwrap_or(0.0)
}

#[derive(Debug, Clone)]
pub struct StatusTracker {
    pub state: String,
    pub since: f64,
    candidate: Option<String>,
    candidate_at: f64,
    /// From OSC 7501, authoritative while fresh.
    pub reported: Option<String>,
    pub reported_at: f64,
    /// After new input, don't fall back to idle/done before the agent reacts.
    pub hold_until: f64,
    /// Last frame that *looked* busy (not the state forced by new input).
    pub detected_working_at: f64,
}

impl Default for StatusTracker {
    fn default() -> Self {
        Self::new("idle", now_secs())
    }
}

impl StatusTracker {
    pub fn new(state: &str, since: f64) -> Self {
        Self {
            state: state.to_string(),
            since,
            candidate: None,
            candidate_at: 0.0,
            reported: None,
            reported_at: 0.0,
            hold_until: 0.0,
            detected_working_at: 0.0,
        }
    }

    /// Why `observe` reads the screen the way it does right now (herdr's `agent explain`), for `rules.test`:
    /// a fresh OSC 7501 report wins, then the first matching rule, else the output-activity fallback. The
    /// fallback never yields `blocked`: only a rule or the agent itself can say it needs you.
    pub fn reason(&self, matched_rule: Option<&str>, has_rule_set: bool, last_output_at: f64, now: f64) -> String {
        if let Some(reported) = &self.reported
            && now - self.reported_at < REPORT_FRESH_SECONDS
        {
            return format!("osc7501_report:{reported}");
        }
        if let Some(rule) = matched_rule {
            return format!("rule:{rule}");
        }
        let why = if has_rule_set { "no_rule_matched" } else { "no_rule_set" };
        let fallback = if now - last_output_at < ACTIVITY_WINDOW { "recent_output_working" } else { "quiet_idle" };
        format!("{why}:fallback_{fallback}")
    }

    /// Feed one detection. Returns the new public state if it changed.
    pub fn observe(&mut self, detected: Option<&str>, last_output_at: f64, focused: bool, now: f64, allow_done: bool) -> Option<String> {
        if self.state == "exited" || self.state == "stopped" {
            return None;
        }
        let mut detected: Option<String> = detected.map(str::to_string);
        if let Some(reported) = &self.reported
            && now - self.reported_at < REPORT_FRESH_SECONDS
        {
            detected = Some(if reported == "done" { "idle".into() } else { reported.clone() });
        }
        let detected = detected.unwrap_or_else(|| {
            if now - last_output_at < ACTIVITY_WINDOW { "working" } else { "idle" }.to_string()
        });
        if detected == "working" || detected == "blocked" {
            self.detected_working_at = now;
        }
        if detected == "idle" && now < self.hold_until {
            return None;
        }
        if self.candidate.as_deref() != Some(detected.as_str()) {
            self.candidate = Some(detected);
            self.candidate_at = now;
            return None;
        }
        if now - self.candidate_at < DEBOUNCE_SECONDS {
            return None;
        }
        let mut target = detected.clone();
        if detected == "idle" && self.state == "working" && !focused && allow_done {
            target = "done".into();
        }
        if detected == "idle" && self.state == "done" {
            return None; // stay done until acknowledged
        }
        if target == self.state {
            return None;
        }
        self.state = target.clone();
        self.since = now;
        Some(target)
    }

    /// A detection differs from the committed state and is still debouncing (`_candidate != state` in Python).
    pub fn has_pending_candidate(&self) -> bool {
        self.candidate.as_deref() != Some(self.state.as_str())
    }

    /// New input = new turn: go working now and hold it for `hold` seconds (`mark_busy` in Python).
    pub fn force_working(&mut self, now: f64, hold: f64) {
        self.state = "working".into();
        self.since = now;
        self.candidate = None;
        self.hold_until = now + hold;
    }

    /// User looked at the pane: done -> idle.
    pub fn acknowledge(&mut self) -> Option<String> {
        if self.state == "done" {
            self.state = "idle".into();
            self.since = now_secs();
            return Some(self.state.clone());
        }
        None
    }

    pub fn report(&mut self, state: &str) {
        self.report_at(state, now_secs());
    }

    pub fn report_at(&mut self, state: &str, now: f64) {
        self.reported = Some(state.to_string());
        self.reported_at = now;
    }

    pub fn mark_exited(&mut self) -> String {
        self.state = "exited".into();
        self.since = now_secs();
        self.state.clone()
    }
}

#[cfg(test)]
#[path = "status_tracker_tests.rs"]
mod tests;
