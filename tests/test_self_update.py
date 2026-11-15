"""Self-update: version comparison, refusal outside a packaged Linux build, and the bundle swap."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from drover.core import self_update


def test_version_tuple_orders_releases():
    assert self_update.version_tuple("v0.1.10") > self_update.version_tuple("0.1.9")
    assert self_update.version_tuple("v1.0.0") > self_update.version_tuple("v0.9.9")
    assert self_update.version_tuple("v0.1.5") == self_update.version_tuple("0.1.5")


def test_apply_refused_when_not_installable(monkeypatch):
    monkeypatch.setattr(self_update, "installable", lambda: False)
    with pytest.raises(self_update.UpdateError):
        self_update.apply("v9.9.9")


def test_apply_rejects_bad_tag(monkeypatch):
    monkeypatch.setattr(self_update, "installable", lambda: True)
    with pytest.raises(self_update.UpdateError):
        self_update.apply("../evil")


def test_apply_swaps_bundle_folder(tmp_path: Path, monkeypatch):
    bundle = tmp_path / "drover"
    bundle.mkdir()
    (bundle / "dr").write_text("old")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = b"new"
        info = tarfile.TarInfo("drover/dr")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    buf.seek(0)
    monkeypatch.setattr(self_update, "installable", lambda: True)
    monkeypatch.setattr(self_update, "bundle_dir", lambda: bundle)
    monkeypatch.setattr(self_update, "arch", lambda: "x64")
    monkeypatch.setattr(self_update.urllib.request, "urlopen", lambda url, timeout=0: buf)
    self_update.apply("v0.2.0")
    assert (bundle / "dr").read_text() == "new"
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".drover-update-")]  # temp dir cleaned up


def _fake_download(payload: bytes):
    return lambda url, timeout=0: io.BytesIO(payload)


def test_windows_exe_swap_keeps_old_copy_and_cleanup_removes_it(tmp_path: Path, monkeypatch):
    exe = tmp_path / "drover.exe"
    exe.write_bytes(b"MZold")
    new = b"MZ" + b"\0" * self_update.MIN_EXE_BYTES
    monkeypatch.setattr(self_update.urllib.request, "urlopen", _fake_download(new))
    self_update.apply_windows_exe("v0.2.0", exe)
    assert exe.read_bytes() == new
    assert (tmp_path / "drover.exe.old").read_bytes() == b"MZold"
    assert not (tmp_path / "drover.exe.new").exists()
    monkeypatch.setattr(self_update, "is_single_exe", lambda: True)
    monkeypatch.setattr(self_update.sys, "executable", str(exe))
    self_update.remove_old_exe()
    assert not (tmp_path / "drover.exe.old").exists()


def test_windows_exe_swap_rejects_a_non_program_download(tmp_path: Path, monkeypatch):
    exe = tmp_path / "drover.exe"
    exe.write_bytes(b"MZold")
    monkeypatch.setattr(self_update.urllib.request, "urlopen", _fake_download(b"<html>Not Found</html>"))
    with pytest.raises(self_update.UpdateError, match="not a Windows program"):
        self_update.apply_windows_exe("v0.2.0", exe)
    assert exe.read_bytes() == b"MZold"
    assert sorted(p.name for p in tmp_path.glob("drover.exe*")) == ["drover.exe"]


def test_windows_single_exe_is_installable(monkeypatch):
    monkeypatch.setattr(self_update, "is_single_exe", lambda: True)
    assert self_update.installable()
