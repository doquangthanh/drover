//! Agent detection rules: bundled TOML files, overridden by same-id user files; evaluated against screen text.
//! Port of `drover/status/detection_rule_loader.py`; evaluation lives in `status_detector.rs`.

use std::path::Path;
use std::sync::LazyLock;

pub use crate::launch_command::{match_agent_kind, split_command};
pub use crate::status_detector::{RuleEvaluation, detect_kind_from_title, evaluate, region_text};

use regex::Regex;
use serde::Deserialize;

const VALID_STATES: [&str; 3] = ["working", "blocked", "idle"];
static REGION_RE: LazyLock<Regex> = LazyLock::new(|| Regex::new(r"^(title|screen|bottom\((\d+)\))$").unwrap());

/// Bundled rule files (single source of truth shared with the Python daemon until it is removed).
pub const BUNDLED_RULES: &[(&str, &str)] = &[
    ("claude.toml", include_str!("../../../../src/drover/status/rules/claude.toml")),
    ("codex.toml", include_str!("../../../../src/drover/status/rules/codex.toml")),
    ("gemini.toml", include_str!("../../../../src/drover/status/rules/gemini.toml")),
    ("opencode.toml", include_str!("../../../../src/drover/status/rules/opencode.toml")),
    ("shell.toml", include_str!("../../../../src/drover/status/rules/shell.toml")),
];

#[derive(Debug, Clone)]
pub struct DetectionRule {
    pub id: String,
    pub state: String,
    pub priority: i64,
    pub region: String,
    pub patterns: Vec<Regex>,
}

#[derive(Debug, Clone)]
pub struct AgentRuleSet {
    pub id: String,
    pub aliases: Vec<String>,
    pub resume: String,
    pub detect_title: Option<Regex>,
    pub rules: Vec<DetectionRule>,
    pub source: String,
    pub path: String,
}

impl AgentRuleSet {
    pub fn names(&self) -> impl Iterator<Item = &str> {
        std::iter::once(self.id.as_str()).chain(self.aliases.iter().map(String::as_str))
    }
}

#[derive(Deserialize)]
#[serde(untagged)]
enum OneOrMany {
    One(String),
    Many(Vec<String>),
}

#[derive(Deserialize)]
struct RawRule {
    id: Option<String>,
    #[serde(default)]
    state: String,
    #[serde(default)]
    priority: i64,
    region: Option<String>,
    regex: Option<OneOrMany>,
}

#[derive(Deserialize)]
struct RawFile {
    id: Option<String>,
    #[serde(default)]
    aliases: Vec<String>,
    #[serde(default)]
    resume: String,
    detect_title: Option<String>,
    #[serde(default)]
    rules: Vec<RawRule>,
}

/// Parse one rule file. `file_name` is used for errors and the default id (its stem).
pub fn parse_rule_text(text: &str, file_name: &str, source: &str, path: &str) -> Result<AgentRuleSet, String> {
    let raw: RawFile = toml::from_str(text).map_err(|e| e.to_string())?;
    let stem = Path::new(file_name).file_stem().and_then(|s| s.to_str()).unwrap_or(file_name);
    let mut rules = Vec::new();
    for (index, item) in raw.rules.into_iter().enumerate() {
        let region = item.region.unwrap_or_else(|| "screen".into());
        if !VALID_STATES.contains(&item.state.as_str()) {
            return Err(format!("{file_name} rule #{index}: bad state {:?}", item.state));
        }
        if !REGION_RE.is_match(&region) {
            return Err(format!("{file_name} rule #{index}: bad region {region:?}"));
        }
        let sources = match item.regex {
            None => vec![],
            Some(OneOrMany::One(s)) => vec![s],
            Some(OneOrMany::Many(v)) => v,
        };
        let patterns = sources
            .iter()
            .map(|p| Regex::new(&format!("(?m){p}")).map_err(|e| e.to_string()))
            .collect::<Result<Vec<_>, _>>()?;
        rules.push(DetectionRule {
            id: item.id.unwrap_or_else(|| format!("rule{index}")),
            state: item.state,
            priority: item.priority,
            region,
            patterns,
        });
    }
    rules.sort_by_key(|r| std::cmp::Reverse(r.priority)); // stable, like Python's sort(reverse=True)
    let detect_title = match raw.detect_title.filter(|t| !t.is_empty()) {
        Some(t) => Some(Regex::new(&t).map_err(|e| e.to_string())?),
        None => None,
    };
    Ok(AgentRuleSet {
        id: raw.id.filter(|i| !i.is_empty()).unwrap_or_else(|| stem.to_string()),
        aliases: raw.aliases,
        resume: raw.resume,
        detect_title,
        rules,
        source: source.into(),
        path: path.into(),
    })
}

/// Bundled sets, then `*.toml` from `user_dir` (sorted by name); a user set replaces the same id in place.
/// Returns the sets in load order and human-readable errors.
pub fn load_rule_sets(user_dir: Option<&Path>) -> (Vec<AgentRuleSet>, Vec<String>) {
    let mut sets: Vec<AgentRuleSet> = Vec::new();
    let mut errors = Vec::new();
    let mut add = |result: Result<AgentRuleSet, String>, name: &str| match result {
        Ok(set) => match sets.iter_mut().find(|s| s.id == set.id) {
            Some(slot) => *slot = set,
            None => sets.push(set),
        },
        Err(e) => errors.push(format!("{name}: {e}")),
    };
    for (name, text) in BUNDLED_RULES {
        add(parse_rule_text(text, name, "bundled", name), name);
    }
    if let Some(dir) = user_dir.filter(|d| d.is_dir()) {
        let mut files: Vec<_> = std::fs::read_dir(dir)
            .into_iter()
            .flatten()
            .flatten()
            .map(|e| e.path())
            .filter(|p| p.extension().is_some_and(|x| x == "toml"))
            .collect();
        files.sort();
        for path in files {
            let name = path.file_name().and_then(|n| n.to_str()).unwrap_or("").to_string();
            let result = std::fs::read_to_string(&path)
                .map_err(|e| e.to_string())
                .and_then(|text| parse_rule_text(&text, &name, "user", &path.to_string_lossy()));
            add(result, &name);
        }
    }
    (sets, errors)
}

#[cfg(test)]
#[path = "detection_rules_tests.rs"]
mod tests;
