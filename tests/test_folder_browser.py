"""Folder picker backend: listing inside allowed roots, refusing escapes, validating new names."""

from __future__ import annotations

from pathlib import Path

import pytest

from herd.core.folder_browser import FolderAccessError, allowed_roots, list_dirs, make_dir


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "projects"
    (root / "alpha" / ".git").mkdir(parents=True)
    (root / "beta").mkdir()
    (root / ".secret").mkdir()
    (root / "notes.txt").write_text("x", encoding="utf-8")
    return root


def test_allowed_roots_defaults_to_home_when_unconfigured():
    assert allowed_roots([]) == [Path.home().resolve()]


def test_lists_only_subfolders_sorted_and_hides_dot_folders(workspace):
    entries = list_dirs(str(workspace), [str(workspace)])["entries"]
    assert [e["name"] for e in entries] == ["alpha", "beta"]
    assert entries[0]["is_git"] is True
    assert entries[1]["is_git"] is False


def test_show_hidden_includes_dot_folders(workspace):
    names = [e["name"] for e in list_dirs(str(workspace), [str(workspace)], show_hidden=True)["entries"]]
    assert ".secret" in names


def test_empty_path_starts_at_first_allowed_root(workspace):
    assert list_dirs("", [str(workspace)])["path"] == str(workspace.resolve())


def test_parent_is_null_at_root_and_points_up_inside_root(workspace):
    assert list_dirs(str(workspace), [str(workspace)])["parent"] is None
    child = list_dirs(str(workspace / "alpha"), [str(workspace)])
    assert child["parent"] == str(workspace.resolve())


def test_refuses_parent_of_allowed_root(workspace):
    with pytest.raises(FolderAccessError, match="outside"):
        list_dirs(str(workspace.parent), [str(workspace)])


def test_refuses_dotdot_escape(workspace):
    with pytest.raises(FolderAccessError):
        list_dirs(str(workspace / ".." / ".."), [str(workspace)])


def test_refuses_sibling_sharing_name_prefix(workspace):
    evil = workspace.parent / "projects-evil"
    evil.mkdir()
    with pytest.raises(FolderAccessError):
        list_dirs(str(evil), [str(workspace)])


def test_file_path_is_not_a_folder(workspace):
    with pytest.raises(FolderAccessError, match="not a folder"):
        list_dirs(str(workspace / "notes.txt"), [str(workspace)])


def test_missing_configured_root_raises_access_error_not_index_error(tmp_path):
    # Expected to FAIL: roots[0] raises IndexError when no configured root exists.
    # Source: herd/core/folder_browser.py:30 (list_dirs, empty path branch).
    with pytest.raises(FolderAccessError):
        list_dirs("", [str(tmp_path / "does-not-exist")])


def test_make_dir_creates_folder_inside_root(workspace):
    created = make_dir(str(workspace), "gamma", [str(workspace)])
    assert Path(created) == (workspace / "gamma").resolve()
    assert (workspace / "gamma").is_dir()


@pytest.mark.parametrize("name", ["", ".", "..", "a/b", "a\\b", "x:y", "q*", "w?", 'a"b', "<x>", "p|q"])
def test_make_dir_rejects_invalid_names(workspace, name):
    with pytest.raises(FolderAccessError, match="invalid folder name"):
        make_dir(str(workspace), name, [str(workspace)])


def test_make_dir_refuses_parent_outside_root(workspace):
    with pytest.raises(FolderAccessError):
        make_dir(str(workspace.parent), "escape", [str(workspace)])
    assert not (workspace.parent / "escape").exists()


def test_make_dir_existing_name_raises_file_exists(workspace):
    with pytest.raises(FileExistsError):
        make_dir(str(workspace), "beta", [str(workspace)])
