"""Windows in-app update: moving the running drover.exe aside when an older copy is still running."""

from pathlib import Path

import pytest

from drover.core import self_update


def _lock(monkeypatch, *locked: Path) -> None:
    """Make unlink fail for `locked` paths, like Windows does for an .exe that is still running."""
    real_unlink = Path.unlink

    def unlink(self, missing_ok=False):
        if self in locked:
            raise PermissionError(13, "Access is denied", str(self))
        return real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", unlink)


def _files(tmp_path: Path, **content: str) -> None:
    for name, text in content.items():
        (tmp_path / name).write_text(text)


def test_swap_uses_plain_old_name(tmp_path):
    _files(tmp_path, **{"drover.exe": "v1", "drover.exe.new": "v2"})
    self_update.swap_in_exe(tmp_path / "drover.exe.new", tmp_path / "drover.exe")
    assert (tmp_path / "drover.exe").read_text() == "v2"
    assert (tmp_path / "drover.exe.old").read_text() == "v1"


def test_swap_skips_an_old_copy_that_is_still_running(tmp_path, monkeypatch):
    _files(tmp_path, **{"drover.exe": "v2", "drover.exe.new": "v3", "drover.exe.old": "v1"})
    _lock(monkeypatch, tmp_path / "drover.exe.old")
    self_update.swap_in_exe(tmp_path / "drover.exe.new", tmp_path / "drover.exe")
    assert (tmp_path / "drover.exe").read_text() == "v3"
    assert (tmp_path / "drover.exe.old").read_text() == "v1"
    assert (tmp_path / "drover.exe.old2").read_text() == "v2"


def test_swap_gives_up_and_cleans_the_download_when_every_name_is_taken(tmp_path, monkeypatch):
    names = ["drover.exe.old"] + [f"drover.exe.old{n}" for n in range(2, self_update.MAX_OLD_EXES + 1)]
    _files(tmp_path, **{"drover.exe": "v2", "drover.exe.new": "v3"}, **{n: "x" for n in names})
    _lock(monkeypatch, *(tmp_path / n for n in names))
    with pytest.raises(self_update.UpdateError):
        self_update.swap_in_exe(tmp_path / "drover.exe.new", tmp_path / "drover.exe")
    assert (tmp_path / "drover.exe").read_text() == "v2"
    assert not (tmp_path / "drover.exe.new").exists()


def test_remove_old_exes_keeps_running_ones(tmp_path, monkeypatch):
    _files(tmp_path, **{"drover.exe": "v3", "drover.exe.old": "v1", "drover.exe.old2": "v2"})
    _lock(monkeypatch, tmp_path / "drover.exe.old")
    self_update.remove_old_exes(tmp_path / "drover.exe")
    assert (tmp_path / "drover.exe.old").exists()
    assert not (tmp_path / "drover.exe.old2").exists()
    assert (tmp_path / "drover.exe").exists()
