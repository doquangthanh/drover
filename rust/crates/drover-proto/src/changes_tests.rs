use crate::changes::*;

const SAMPLE: &str = "diff --git a/f b/f\nindex 1..2 100644\n--- a/f\n+++ b/f\n@@ -10,3 +20,3 @@ fn\n keep\n-gone\n+new\n tail";

#[test]
fn no_rows_for_empty_or_header_only_text() {
    assert!(parse_diff("").is_empty());
    assert!(parse_diff("diff --git a/x b/x\nindex 1..2\n--- a/x\n+++ b/x").is_empty());
}

#[test]
fn drops_file_headers_and_keeps_the_hunk_header() {
    let rows = parse_diff(SAMPLE);
    assert_eq!(rows[0], DiffRow { kind: RowKind::Hunk, text: "@@ -10,3 +20,3 @@ fn".into(), n: None });
    assert_eq!(rows.len(), 5);
}

#[test]
fn numbers_context_and_added_by_new_line_and_removed_by_old_line() {
    let rows = parse_diff(SAMPLE);
    let n: Vec<(RowKind, Option<u32>)> = rows[1..].iter().map(|r| (r.kind, r.n)).collect();
    assert_eq!(n, [(RowKind::Context, Some(20)), (RowKind::Removed, Some(11)), (RowKind::Added, Some(21)), (RowKind::Context, Some(22))]);
}

#[test]
fn keeps_blank_context_lines_visible() {
    let rows = parse_diff("@@ -1 +1 @@\n\n+x");
    assert_eq!(rows[1].text, "  ");
}

#[test]
fn base_and_shown_worktree() {
    let t = |p: &str, b: &str, missing: bool| Worktree { path: p.into(), branch: Some(b.into()), changes: None, missing };
    let trees = vec![t("/r", "main", false), t("/r-a", "task-a", true), t("/r-b", "task-b", false)];
    assert_eq!(base("", &trees), "main");
    assert_eq!(base(" dev ", &trees), "dev");
    assert_eq!(shown_path(None, &trees).as_deref(), Some("/r-b"), "first live task worktree");
    assert_eq!(shown_path(Some("/r-a"), &trees).as_deref(), Some("/r-b"), "a deleted one cannot be shown");
    assert_eq!(shown_path(Some("/r"), &trees).as_deref(), Some("/r"));
    assert_eq!(split_path("src/a/b.rs"), ("b.rs", "src/a/"));
}
