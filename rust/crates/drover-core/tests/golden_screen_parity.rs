//! Raw PTY captures (120x40) must render to the same visible text as the Python daemon's pyte screen.
//! Exception: `nano-killed-alt-screen` expects the restored primary screen (pyte has no alternate screen, so its
//! old output was wrong there); see plans/261118-0820-rust-full-rewrite/reports/phase-02-gate-spike-results.md.

use drover_core::screen::PaneScreen;

fn check(name: &str) {
    let dir = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/golden/");
    let raw = std::fs::read(format!("{dir}{name}.raw")).unwrap();
    let expected = std::fs::read_to_string(format!("{dir}{name}.expected.txt")).unwrap();
    let mut screen = PaneScreen::new(120, 40, 5000);
    screen.feed(&raw);
    let got = screen.visible_lines().join("\n") + "\n";
    assert_eq!(got, expected, "{name} differs");
}

#[test]
fn shell_colors_and_wide_chars() {
    check("shell");
}

#[test]
fn claude_startup_dialog() {
    check("claude");
}

#[test]
fn nano_killed_restores_primary_screen() {
    check("nano-killed-alt-screen");
}
