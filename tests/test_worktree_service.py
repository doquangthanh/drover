"""Git worktree service against a real temporary repository."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from git_helpers import run_git
from herd.git import worktree_service as wt
from herd.git.worktree_service import GitError


async def test_repo_info_describes_clean_repo(git_repo):
    info = await wt.repo_info(str(git_repo))
    assert info["is_repo"] is True
    assert os.path.samefile(info["root"], git_repo)
    assert info["branch"] == "main"
    assert info["dirty"] == 0


async def test_repo_info_counts_uncommitted_files(git_repo):
    (git_repo / "scratch.txt").write_text("x", encoding="utf-8")
    (git_repo / "README.md").write_text("changed\n", encoding="utf-8")
    assert (await wt.repo_info(str(git_repo)))["dirty"] == 2


async def test_repo_info_reports_plain_folder_as_non_repo(tmp_path):
    plain = tmp_path / "plain"
    plain.mkdir()
    assert await wt.repo_info(str(plain)) == {"is_repo": False}


async def test_repo_info_reports_missing_folder_as_non_repo(tmp_path):
    assert await wt.repo_info(str(tmp_path / "missing")) == {"is_repo": False}


@pytest.mark.parametrize("raw, slug", [
    ("Add Login Form!", "add-login-form"),
    ("  Fix: parser / bug  ", "fix-parser-bug"),
    ("v1.2_hotfix", "v1.2_hotfix"),
])
def test_safe_task_name_slugifies(raw, slug):
    assert wt.safe_task_name(raw) == slug


def test_safe_task_name_rejects_empty_and_truncates():
    with pytest.raises(GitError, match="empty"):
        wt.safe_task_name("!!!")
    assert len(wt.safe_task_name("a" * 100)) == 60


async def test_create_worktree_makes_hd_branch_in_sibling_folder(git_repo):
    info = await wt.create_worktree(str(git_repo), "Add Login")
    assert info["branch"] == "hd/add-login"
    assert info["base"] == "main"
    path = Path(info["path"])
    assert path.is_dir()
    assert path.parent.name == f"{git_repo.name}-wt"
    assert (path / "README.md").exists()


async def test_list_worktrees_shows_main_and_task(git_repo):
    await wt.create_worktree(str(git_repo), "Task One")
    items = await wt.list_worktrees(str(git_repo))
    assert sorted(i.get("branch", "") for i in items) == ["hd/task-one", "main"]
    assert all(i["changes"] == 0 for i in items)


async def test_duplicate_worktree_is_refused(git_repo):
    await wt.create_worktree(str(git_repo), "dup")
    with pytest.raises(GitError, match="already exists"):
        await wt.create_worktree(str(git_repo), "dup")


async def test_changed_files_counts_committed_and_uncommitted(git_repo):
    info = await wt.create_worktree(str(git_repo), "feature")
    wt_path = info["path"]
    (Path(wt_path) / "new.py").write_text("a = 1\nb = 2\n", encoding="utf-8")
    run_git(wt_path, "add", "new.py")
    run_git(wt_path, "commit", "-m", "add new module")
    (Path(wt_path) / "README.md").write_text("hello\nmore\n", encoding="utf-8")

    files = {f["path"]: f for f in await wt.changed_files(wt_path, "main")}
    assert files["new.py"]["added"] == 2
    assert files["README.md"]["added"] == 1

    diff = await wt.file_diff(wt_path, "main", "README.md")
    assert "+more" in diff


async def test_remove_refuses_dirty_worktree_then_force_removes(git_repo):
    info = await wt.create_worktree(str(git_repo), "dirty-task")
    path = info["path"]
    (Path(path) / "wip.txt").write_text("work in progress", encoding="utf-8")
    with pytest.raises(GitError, match="uncommitted"):
        await wt.remove_worktree(path)
    assert Path(path).is_dir()
    await wt.remove_worktree(path, force=True)
    assert not Path(path).exists()


async def test_remove_clean_worktree_without_force(git_repo):
    info = await wt.create_worktree(str(git_repo), "clean-task")
    await wt.remove_worktree(info["path"])
    assert not Path(info["path"]).exists()
    assert "hd/clean-task" not in [i.get("branch") for i in await wt.list_worktrees(str(git_repo))]


async def test_remove_refuses_main_working_tree(git_repo):
    with pytest.raises(GitError, match="main working tree"):
        await wt.remove_worktree(str(git_repo))
    assert git_repo.is_dir()
