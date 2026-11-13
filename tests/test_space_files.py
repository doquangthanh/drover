"""Files view backend: browse/read inside a space, refuse escapes, report git changes."""

from __future__ import annotations

import os

import pytest
from git_helpers import run_git

from herd.core import space_files as sf
from herd.git import worktree_service as wt


def test_list_dir_puts_folders_first_and_hides_dot_git(git_repo):
    (git_repo / "src").mkdir()
    (git_repo / "src" / "a.py").write_text("x", encoding="utf-8")
    (git_repo / "zeta.txt").write_text("x", encoding="utf-8")
    entries = sf.list_dir(str(git_repo))["entries"]
    names = [e["name"] for e in entries]
    assert ".git" not in names
    assert names.index("src") < names.index("README.md") < names.index("zeta.txt")
    assert next(e for e in entries if e["name"] == "src")["dir"] is True
    assert sf.list_dir(str(git_repo), "src")["entries"][0]["path"] == "src/a.py"


@pytest.mark.parametrize("rel", ["..", "../x", "src/../../x"])
def test_paths_cannot_leave_the_space(git_repo, rel):
    (git_repo / "src").mkdir()
    with pytest.raises(sf.FileAccessError):
        sf.read_text(str(git_repo), rel)
    with pytest.raises(sf.FileAccessError):
        sf.list_dir(str(git_repo), rel)


def test_absolute_path_cannot_leave_the_space(git_repo, tmp_path):
    outside = tmp_path / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    with pytest.raises(sf.FileAccessError):
        sf.read_text(str(git_repo), str(outside))


def test_read_text_returns_content_and_line_count(git_repo):
    (git_repo / "a.txt").write_bytes(b"one\ntwo\nthree\n")  # bytes: Windows text mode would add \r
    out = sf.read_text(str(git_repo), "a.txt")
    assert (out["text"], out["lines"], out["truncated"], out["binary"]) == ("one\ntwo\nthree\n", 3, False, False)


def test_read_text_flags_binary_files(git_repo):
    (git_repo / "pic.bin").write_bytes(b"\x89PNG\x00\x01\x02")
    assert sf.read_text(str(git_repo), "pic.bin")["binary"] is True


def test_read_text_truncates_large_files(git_repo):
    (git_repo / "big.txt").write_text("x" * (sf.MAX_BYTES + 500), encoding="utf-8")
    out = sf.read_text(str(git_repo), "big.txt")
    assert out["truncated"] is True and len(out["text"]) == sf.MAX_BYTES


def test_read_text_rejects_folders(git_repo):
    with pytest.raises(sf.FileAccessError):
        sf.read_text(str(git_repo), "")


async def test_status_map_reports_modified_added_and_untracked(git_repo):
    (git_repo / "README.md").write_text("changed\n", encoding="utf-8")
    (git_repo / "new.txt").write_text("n", encoding="utf-8")
    (git_repo / "staged.txt").write_text("s", encoding="utf-8")
    run_git(git_repo, "add", "staged.txt")
    status = await wt.status_map(str(git_repo))
    assert status["is_repo"] is True
    assert status["files"] == {"README.md": "M", "new.txt": "?", "staged.txt": "A"}


async def test_status_map_paths_are_relative_to_a_subfolder(git_repo):
    sub = git_repo / "pkg"
    sub.mkdir()
    (sub / "mod.py").write_text("x", encoding="utf-8")
    run_git(git_repo, "add", "-A")
    run_git(git_repo, "commit", "-m", "pkg")
    (sub / "mod.py").write_text("y", encoding="utf-8")
    (git_repo / "README.md").write_text("changed\n", encoding="utf-8")  # outside the subfolder
    assert (await wt.status_map(str(sub)))["files"] == {"mod.py": "M"}


async def test_status_map_for_plain_folder_is_not_a_repo(tmp_path):
    assert await wt.status_map(str(tmp_path)) == {"is_repo": False, "files": {}}


# ---- writing -----------------------------------------------------------------------------------

def test_write_replaces_file_and_returns_new_mtime(git_repo):
    (git_repo / "a.txt").write_bytes(b"old\n")
    before = sf.read_text(str(git_repo), "a.txt")["mtime_us"]
    out = sf.write_text(str(git_repo), "a.txt", "new\nline\n", base_mtime_us=before)
    assert (git_repo / "a.txt").read_bytes() == b"new\nline\n"  # exact bytes, no newline translation
    assert out["size"] == 9
    assert not list(git_repo.glob(".*.herd-tmp"))


def test_write_keeps_crlf_files_intact(git_repo):
    (git_repo / "win.txt").write_bytes(b"a\r\nb\r\n")
    sf.write_text(str(git_repo), "win.txt", "a\r\nb\r\nc\r\n")
    assert (git_repo / "win.txt").read_bytes() == b"a\r\nb\r\nc\r\n"


def test_write_refuses_when_file_changed_on_disk(git_repo):
    (git_repo / "a.txt").write_bytes(b"v1")
    loaded = sf.read_text(str(git_repo), "a.txt")["mtime_us"]
    os.utime(git_repo / "a.txt", ns=(1, 1))  # an agent touched it meanwhile
    with pytest.raises(sf.FileConflict):
        sf.write_text(str(git_repo), "a.txt", "mine", base_mtime_us=loaded)
    assert (git_repo / "a.txt").read_bytes() == b"v1"
    sf.write_text(str(git_repo), "a.txt", "mine", base_mtime_us=loaded, force=True)  # "overwrite anyway"
    assert (git_repo / "a.txt").read_bytes() == b"mine"


def test_write_create_makes_new_file_and_folders_but_never_overwrites(git_repo):
    sf.write_text(str(git_repo), "deep/er/new.py", "x = 1\n", create=True)
    assert (git_repo / "deep" / "er" / "new.py").read_text(encoding="utf-8") == "x = 1\n"
    with pytest.raises(sf.FileAccessError):
        sf.write_text(str(git_repo), "README.md", "boom", create=True)


@pytest.mark.parametrize("rel", ["../evil.txt", "src/../../evil.txt", ".git/config", ".GIT/hooks/pre-commit", ""])
def test_write_cannot_escape_or_touch_git_internals(git_repo, rel):
    with pytest.raises(sf.FileAccessError):
        sf.write_text(str(git_repo), rel, "x", create=True)


def test_write_rejects_absolute_paths_outside_space(git_repo, tmp_path):
    with pytest.raises(sf.FileAccessError):
        sf.write_text(str(git_repo), str(tmp_path / "x.txt"), "x", create=True)
    assert not (tmp_path / "x.txt").exists()


def test_non_utf8_and_truncated_files_open_read_only(git_repo):
    (git_repo / "latin.txt").write_bytes("caf\xe9".encode("latin-1"))
    assert sf.read_text(str(git_repo), "latin.txt")["editable"] is False
    (git_repo / "big.txt").write_text("x" * (sf.MAX_BYTES + 5), encoding="utf-8")
    assert sf.read_text(str(git_repo), "big.txt")["editable"] is False
    (git_repo / "ok.txt").write_bytes(b"fine")
    assert sf.read_text(str(git_repo), "ok.txt")["editable"] is True
