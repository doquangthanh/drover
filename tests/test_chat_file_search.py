"""@ picker backend: git-aware file listing and ranking."""

from __future__ import annotations

from git_helpers import run_git

from herd.chat import file_search as fs

FILES = ["src/app/pricing.tsx", "src/app/page.tsx", "src/components/plan-card.tsx", "README.md", "docs/pricing-notes.md", "a/b/c/deep.txt"]


def test_exact_name_then_prefix_then_contains_then_path():
    assert fs.rank_files(FILES, "pricing")[:2] == ["src/app/pricing.tsx", "docs/pricing-notes.md"]
    assert fs.rank_files(FILES, "page.tsx")[0] == "src/app/page.tsx"
    assert fs.rank_files(FILES, "card")[0] == "src/components/plan-card.tsx"
    assert fs.rank_files(FILES, "components/plan")[0] == "src/components/plan-card.tsx"


def test_letters_in_order_match_and_no_match():
    assert "src/components/plan-card.tsx" in fs.rank_files(FILES, "scpc")
    assert fs.rank_files(FILES, "zzzz") == []


def test_empty_query_lists_shallow_files_first_and_limit_applies():
    assert fs.rank_files(FILES, "")[0] == "README.md"
    assert len(fs.rank_files(FILES, "", limit=2)) == 2


def test_query_is_case_and_slash_insensitive():
    assert fs.rank_files(FILES, "SRC\\App\\Page")[0] == "src/app/page.tsx"


def test_git_repo_lists_tracked_and_new_files_but_not_ignored_ones(git_repo):
    (git_repo / ".gitignore").write_text("secret.txt\n", encoding="utf-8")
    (git_repo / "secret.txt").write_text("x", encoding="utf-8")
    (git_repo / "new.txt").write_text("x", encoding="utf-8")
    run_git(git_repo, "add", ".gitignore")
    fs._cache.clear()
    files = fs.list_files(str(git_repo))
    assert "README.md" in files and "new.txt" in files and "secret.txt" not in files


def test_plain_folder_is_walked_skipping_heavy_directories(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x", encoding="utf-8")
    (tmp_path / "node_modules" / "pkg").mkdir(parents=True)
    (tmp_path / "node_modules" / "pkg" / "i.js").write_text("x", encoding="utf-8")
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "h.txt").write_text("x", encoding="utf-8")
    fs._cache.clear()
    assert fs.list_files(str(tmp_path)) == ["src/a.py"]


def test_listing_is_cached_for_a_few_seconds(tmp_path):
    (tmp_path / "one.txt").write_text("x", encoding="utf-8")
    fs._cache.clear()
    assert fs.list_files(str(tmp_path), now=100.0) == ["one.txt"]
    (tmp_path / "two.txt").write_text("x", encoding="utf-8")
    assert fs.list_files(str(tmp_path), now=101.0) == ["one.txt"]
    assert sorted(fs.list_files(str(tmp_path), now=100.0 + fs.CACHE_SECONDS + 1)) == ["one.txt", "two.txt"]
