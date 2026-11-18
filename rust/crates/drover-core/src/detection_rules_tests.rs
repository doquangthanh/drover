//! Ported from `tests/test_detection_rules_bundled.py`.

use super::*;

fn lines(v: &[&str]) -> Vec<String> {
    v.iter().map(|s| s.to_string()).collect()
}

const PERMISSION_SCREEN: &[&str] = &[
    "⏺ Bash(rm -rf build/)",
    "  ⎿  Running…",
    "",
    " Bash command",
    "",
    "   rm -rf build/",
    "   Delete build output",
    "",
    " Do you want to proceed?",
    " ❯ 1. Yes",
    "   2. Yes, and don't ask again for rm commands in /repo",
    "   3. No, and tell Claude what to do differently (esc)",
    "",
    "  Esc to cancel",
];

const WORKING_SCREEN: &[&str] =
    &["⏺ Reading src/app.py", "", "✻ Pondering… (14s · ↑ 1.2k tokens · esc to interrupt)", "", "> ", "  ? for shortcuts"];

const THEME_PICKER_SCREEN: &[&str] = &[
    "Welcome to Claude Code!",
    "",
    "Choose the text style that looks best with your terminal",
    "To change this later, run /theme",
    "",
    " ❯ 1. Dark mode ✔",
    "   2. Light mode",
    "   3. Dark mode (colorblind-friendly)",
    "",
    "  [code preview]",
];

const PLAIN_PROMPT_SCREEN: &[&str] = &["$ ls", "README.md  src", "> ", "  ? for shortcuts"];

fn sets() -> Vec<AgentRuleSet> {
    let (sets, errors) = load_rule_sets(None);
    assert!(errors.is_empty(), "{errors:?}");
    sets
}

fn claude(sets: &[AgentRuleSet]) -> &AgentRuleSet {
    sets.iter().find(|s| s.id == "claude").unwrap()
}

fn matched_ids(results: &[RuleEvaluation]) -> Vec<&str> {
    results.iter().filter(|r| r.matched).map(|r| r.rule_id.as_str()).collect()
}

#[test]
fn bundled_rule_sets_all_load() {
    let sets = sets();
    for id in ["claude", "codex", "gemini", "opencode", "shell"] {
        assert!(sets.iter().any(|s| s.id == id), "{id} missing");
    }
    assert!(sets.iter().all(|s| s.source == "bundled"));
}

#[test]
fn rules_are_sorted_by_priority_descending() {
    let sets = sets();
    let p: Vec<i64> = claude(&sets).rules.iter().map(|r| r.priority).collect();
    let mut sorted = p.clone();
    sorted.sort_by(|a, b| b.cmp(a));
    assert_eq!(p, sorted);
    assert_eq!(claude(&sets).rules[0].id, "permission_prompt");
}

#[test]
fn permission_prompt_is_blocked() {
    let sets = sets();
    let (winner, results) = evaluate(Some(claude(&sets)), "", &lines(PERMISSION_SCREEN));
    assert_eq!(winner.as_deref(), Some("blocked"));
    assert!(matched_ids(&results).contains(&"permission_prompt"));
}

#[test]
fn do_you_want_to_proceed_alone_is_blocked() {
    let sets = sets();
    let screen = lines(&["Do you want to make this edit to app.py?"]);
    assert_eq!(evaluate(Some(claude(&sets)), "", &screen).0.as_deref(), Some("blocked"));
}

#[test]
fn esc_to_interrupt_line_means_working() {
    let sets = sets();
    assert_eq!(evaluate(Some(claude(&sets)), "", &lines(WORKING_SCREEN)).0.as_deref(), Some("working"));
}

#[test]
fn permission_prompt_outranks_working_line() {
    let sets = sets();
    let mut screen = lines(WORKING_SCREEN);
    screen.extend(lines(&PERMISSION_SCREEN[8..]));
    assert_eq!(evaluate(Some(claude(&sets)), "", &screen).0.as_deref(), Some("blocked"));
}

#[test]
fn first_run_theme_picker_is_blocked() {
    let sets = sets();
    let (winner, results) = evaluate(Some(claude(&sets)), "", &lines(THEME_PICKER_SCREEN));
    assert_eq!(winner.as_deref(), Some("blocked"));
    assert!(matched_ids(&results).contains(&"selection_menu"));
}

#[test]
fn plain_prompt_is_idle() {
    let sets = sets();
    assert_eq!(evaluate(Some(claude(&sets)), "", &lines(PLAIN_PROMPT_SCREEN)).0.as_deref(), Some("idle"));
}

#[test]
fn unrelated_output_matches_no_rule() {
    let sets = sets();
    let (winner, results) = evaluate(Some(claude(&sets)), "", &lines(&["PS C:\\> dir", "file.txt"]));
    assert_eq!(winner, None);
    assert!(results.iter().all(|r| !r.matched));
}

#[test]
fn spinner_in_title_is_working() {
    let sets = sets();
    assert_eq!(evaluate(Some(claude(&sets)), "⠂ Claude Code", &lines(&["hi"])).0.as_deref(), Some("working"));
}

#[test]
fn idle_star_title_is_not_working() {
    let sets = sets();
    let got = evaluate(Some(claude(&sets)), "✳ Hỏi đáp chung", &lines(&["❯ xóa dòng đó đi"])).0;
    assert_eq!(got.as_deref(), Some("idle"));
}

#[test]
fn evaluate_without_rule_set_returns_no_verdict() {
    assert_eq!(evaluate(None, "", &lines(&["x"])), (None, vec![]));
}

#[test]
fn detect_kind_from_title_works() {
    let sets = sets();
    assert_eq!(detect_kind_from_title("✳ Claude Code", &sets).as_deref(), Some("claude"));
    assert_eq!(detect_kind_from_title("PS C:\\repo", &sets), None);
}

#[test]
fn match_agent_kind_maps_launch_command() {
    let sets = sets();
    for (command, expected) in [
        ("C:/x/claude.cmd --continue", "claude"),
        ("claude", "claude"),
        ("claude-code --resume", "claude"),
        ("codex resume --last", "codex"),
        ("bash -l", "shell"),
        ("cmd /c echo hi", "shell"),
        ("", "shell"),
        ("unknown-agent", "shell"),
    ] {
        assert_eq!(match_agent_kind(command, &sets), expected, "{command}");
    }
}

#[test]
fn match_agent_kind_handles_quoted_path_with_spaces() {
    let sets = sets();
    assert_eq!(match_agent_kind("\"C:/Program Files/Claude/claude.exe\" --continue", &sets), "claude");
}

fn temp_dir(name: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("drover-rules-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

#[test]
fn user_rule_file_overrides_bundled_by_id() {
    let dir = temp_dir("override");
    std::fs::write(dir.join("claude.toml"), "id = \"claude\"\n[[rules]]\nid = \"custom\"\nstate = \"idle\"\nregex = [\"custom\"]\n").unwrap();
    let (sets, errors) = load_rule_sets(Some(&dir));
    assert!(errors.is_empty(), "{errors:?}");
    let c = claude(&sets);
    assert_eq!(c.source, "user");
    assert_eq!(c.rules.len(), 1);
    assert_eq!(sets[0].id, "claude", "override keeps the bundled position");
}

#[test]
fn invalid_user_rule_files_are_reported_not_fatal() {
    let dir = temp_dir("invalid");
    std::fs::write(dir.join("broken.toml"), "id = \"broken\"\n[[rules]]\nstate = \"angry\"\nregex = [\"x\"]\n").unwrap();
    std::fs::write(dir.join("badre.toml"), "id = \"badre\"\n[[rules]]\nstate = \"idle\"\nregex = [\"(\"]\n").unwrap();
    let (sets, errors) = load_rule_sets(Some(&dir));
    assert!(!sets.iter().any(|s| s.id == "broken" || s.id == "badre"));
    assert_eq!(errors.len(), 2);
    assert!(sets.iter().any(|s| s.id == "claude"));
}

#[test]
fn parse_rule_file_rejects_unknown_region() {
    let text = "id = \"x\"\n[[rules]]\nstate = \"idle\"\nregion = \"sidebar\"\nregex = [\"x\"]\n";
    let err = parse_rule_text(text, "x.toml", "user", "x.toml").unwrap_err();
    assert!(err.contains("bad region"), "{err}");
}
