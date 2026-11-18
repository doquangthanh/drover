//! Evaluate detection rules against a pane's screen text and title. Port of `drover/status/status_detector.py`.

use crate::detection_rules::AgentRuleSet;

#[derive(Debug, Clone, PartialEq)]
pub struct RuleEvaluation {
    pub rule_id: String,
    pub priority: i64,
    pub region: String,
    pub state: String,
    pub matched: bool,
}

pub fn region_text(region: &str, title: &str, lines: &[String]) -> String {
    match region {
        "title" => title.to_string(),
        "screen" => lines.join("\n"),
        _ => {
            let count = region
                .strip_prefix("bottom(")
                .and_then(|r| r.strip_suffix(')'))
                .and_then(|n| n.parse::<usize>().ok())
                .unwrap_or(12);
            let non_empty: Vec<&str> = lines.iter().map(String::as_str).filter(|l| !l.trim().is_empty()).collect();
            non_empty[non_empty.len().saturating_sub(count)..].join("\n")
        }
    }
}

/// (winning state or None, per-rule results in priority order).
pub fn evaluate(rule_set: Option<&AgentRuleSet>, title: &str, lines: &[String]) -> (Option<String>, Vec<RuleEvaluation>) {
    let mut results = Vec::new();
    let mut winner = None;
    let Some(set) = rule_set else { return (None, results) };
    for rule in &set.rules {
        let text = region_text(&rule.region, title, lines);
        let matched = rule.patterns.iter().any(|p| p.is_match(&text));
        results.push(RuleEvaluation {
            rule_id: rule.id.clone(),
            priority: rule.priority,
            region: rule.region.clone(),
            state: rule.state.clone(),
            matched,
        });
        if matched && winner.is_none() {
            winner = Some(rule.state.clone());
        }
    }
    (winner, results)
}

pub fn detect_kind_from_title(title: &str, sets: &[AgentRuleSet]) -> Option<String> {
    sets.iter().find(|s| s.detect_title.as_ref().is_some_and(|re| re.is_match(title))).map(|s| s.id.clone())
}
