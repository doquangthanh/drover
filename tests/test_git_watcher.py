"""Git branch / change count shown in the UI: one-call status, background refresh, snapshot contents."""

from __future__ import annotations

from git_helpers import run_git

from drover.core.git_watcher import GitWatcher
from drover.git import worktree_service as wt


async def test_quick_status_reports_branch_dirty_and_ahead(git_repo, tmp_path):
    assert await wt.quick_status(str(git_repo)) == {"branch": "main", "dirty": 0, "ahead": 0}
    (git_repo / "a.txt").write_text("x", encoding="utf-8")
    (git_repo / "README.md").write_text("changed\n", encoding="utf-8")
    assert (await wt.quick_status(str(git_repo)))["dirty"] == 2
    clone = tmp_path / "clone"
    run_git(tmp_path, "clone", str(git_repo), str(clone))
    for key, value in (("user.email", "qa@example.com"), ("user.name", "drover-qa"), ("commit.gpgsign", "false")):
        run_git(clone, "config", key, value)
    (clone / "n.txt").write_text("n", encoding="utf-8")
    run_git(clone, "add", "-A")
    run_git(clone, "commit", "-m", "n")
    run_git(clone, "checkout", "-b", "feature/x")
    run_git(clone, "branch", "--set-upstream-to=origin/main")
    assert await wt.quick_status(str(clone)) == {"branch": "feature/x", "dirty": 0, "ahead": 1}


async def test_quick_status_is_none_for_plain_and_missing_folders(tmp_path):
    assert await wt.quick_status(str(tmp_path)) is None
    assert await wt.quick_status(str(tmp_path / "gone")) is None


async def test_watcher_puts_branch_into_the_state_the_ui_receives(start_daemon, git_repo):
    daemon = await start_daemon()
    manager = daemon.ctx.manager
    space = manager.ensure_space(str(git_repo))
    watcher = GitWatcher(manager)

    assert await watcher.refresh_once() is True
    entry = next(s for s in daemon.ctx.combined_state()["spaces"] if s["id"] == space.id)
    assert (entry["branch"], entry["dirty"], entry["ahead"]) == ("main", 0, 0)

    assert await watcher.refresh_once() is False  # nothing changed: no state push
    run_git(git_repo, "checkout", "-b", "feature/login")
    (git_repo / "new.txt").write_text("x", encoding="utf-8")
    assert await watcher.refresh_once() is True
    entry = next(s for s in daemon.ctx.combined_state()["spaces"] if s["id"] == space.id)
    assert (entry["branch"], entry["dirty"]) == ("feature/login", 1)


async def test_watcher_leaves_non_git_spaces_without_a_branch(start_daemon, tmp_path):
    daemon = await start_daemon()
    space = daemon.ctx.manager.ensure_space(str(tmp_path))
    await GitWatcher(daemon.ctx.manager).refresh_once()
    entry = next(s for s in daemon.ctx.combined_state()["spaces"] if s["id"] == space.id)
    assert "branch" not in entry
