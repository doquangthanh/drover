"""Self-update: version comparison, refusal outside a packaged Linux build, and the bundle swap."""

from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from herd.core import self_update


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
    bundle = tmp_path / "herd"
    bundle.mkdir()
    (bundle / "hd").write_text("old")
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = b"new"
        info = tarfile.TarInfo("herd/hd")
        info.size = len(data)
        tar.addfile(info, io.BytesIO(data))
    buf.seek(0)
    monkeypatch.setattr(self_update, "installable", lambda: True)
    monkeypatch.setattr(self_update, "bundle_dir", lambda: bundle)
    monkeypatch.setattr(self_update, "arch", lambda: "x64")
    monkeypatch.setattr(self_update.urllib.request, "urlopen", lambda url, timeout=0: buf)
    self_update.apply("v0.2.0")
    assert (bundle / "hd").read_text() == "new"
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".herd-update-")]  # temp dir cleaned up
