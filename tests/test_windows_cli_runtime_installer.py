"""Fast `dr` on Windows: runtime install from the CLI zip (zip-slip safe), shim body, Claude hook command.

Frozen drover.exe is simulated by patching `is_single_exe` where imported and `sys.executable`.
Downloads come from a local zip by replacing `self_update.download`; no network.
"""

from __future__ import annotations

import os
import shutil
import sys
import zipfile
from pathlib import Path

import pytest

from drover import self_command
from drover.core import claude_subagent_hooks, self_update
from drover.core import windows_cli_runtime_installer as rt
from drover.core.windows_cli_runtime_installer import ZIP_NAME

VERSION = "0.1.5"  # release-style version: ensure_runtime() only installs tagged releases
PAYLOAD = os.urandom(self_update.MIN_EXE_BYTES + 1_000)  # incompressible: zip file itself > MIN_EXE_BYTES
ZIP_URL_SUFFIX = f"/releases/download/v{VERSION}/{ZIP_NAME}"


def make_zip(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return path


def make_runtime(version: str = VERSION, *, complete: bool = True) -> Path:
    folder = rt.runtime_dir(version)
    folder.mkdir(parents=True)
    (folder / "dr.exe").write_bytes(b"dr")
    if complete:
        (folder / rt.DONE_MARKER).write_text(version, encoding="utf-8")
    return folder


def root_entries() -> list[str]:
    root = rt.runtime_root()
    return sorted(p.name for p in root.iterdir()) if root.exists() else []


class FakeDownload:
    """Replaces self_update.download: copies `src` (or fails) and logs each URL."""

    def __init__(self) -> None:
        self.src: Path | None = None
        self.urls: list[str] = []
        self.fail = False

    def __call__(self, url: str, dest: Path) -> None:
        self.urls.append(url)
        if self.fail:
            raise self_update.UpdateError("download failed: offline")
        shutil.copyfile(self.src, dest)


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> FakeDownload:
    fake = FakeDownload()
    monkeypatch.setattr(self_update, "download", fake)
    return fake


@pytest.fixture
def frozen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Pretend to be the onefile drover.exe on Windows; returns its path (sys.executable)."""
    exe = tmp_path / "drover.exe"
    monkeypatch.setattr(sys, "executable", str(exe))
    monkeypatch.setattr(rt, "is_single_exe", lambda: True)
    monkeypatch.setattr(self_command, "is_single_exe", lambda: True)
    return exe


# --- runtime location --------------------------------------------------------

def test_runtime_dr_exe_needs_folder_and_marker():
    assert rt.runtime_dr_exe() is None
    folder = make_runtime(complete=False)
    assert rt.runtime_dr_exe() is None  # half-extracted folder is never used
    (folder / rt.DONE_MARKER).write_text(VERSION, encoding="utf-8")
    assert rt.runtime_dr_exe() == folder / "dr.exe"


# --- ensure_runtime ----------------------------------------------------------

def test_ensure_runtime_installs_then_is_noop(frozen, served, tmp_path):
    served.src = make_zip(tmp_path / "cli.zip", {"dr.exe": PAYLOAD, "_internal/base.dll": b"lib"})
    assert rt.ensure_runtime(VERSION) is True
    folder = rt.runtime_dir(VERSION)
    assert (folder / "dr.exe").read_bytes() == PAYLOAD
    assert (folder / "_internal" / "base.dll").read_bytes() == b"lib"
    assert (folder / rt.DONE_MARKER).is_file()
    assert root_entries() == [VERSION]  # download archive removed after install
    assert len(served.urls) == 1 and served.urls[0].endswith(ZIP_URL_SUFFIX)

    assert rt.ensure_runtime(VERSION) is True
    assert len(served.urls) == 1  # already installed: no second download


@pytest.mark.parametrize("version", ["0.1.5.dev0", "main"])
def test_ensure_runtime_skips_dev_versions(frozen, served, version):
    assert rt.ensure_runtime(version) is False
    assert served.urls == []


def test_ensure_runtime_noop_when_not_single_exe(served, monkeypatch):
    monkeypatch.setattr(rt, "is_single_exe", lambda: False)
    assert rt.ensure_runtime(VERSION) is False
    assert served.urls == []

def test_download_failure_returns_false_and_leaves_nothing(frozen, served):
    served.fail = True
    assert rt.ensure_runtime(VERSION) is False
    assert rt.runtime_dr_exe() is None
    assert root_entries() == []


UNSAFE_ARCHIVES = {
    "zip-slip": {"dr.exe": PAYLOAD, "../evil.txt": b"x"},
    "absolute-posix": {"dr.exe": PAYLOAD, "/evil.txt": b"x"},
    "absolute-drive": {"dr.exe": PAYLOAD, "C:/evil.txt": b"x"},
    "nested-dr-exe": {"sub/dr.exe": PAYLOAD},
    "no-dr-exe": {"drover.exe": PAYLOAD},
    "too-small": {"dr.exe": b"tiny"},
}


@pytest.mark.parametrize("entries", UNSAFE_ARCHIVES.values(), ids=UNSAFE_ARCHIVES.keys())
def test_unsafe_or_invalid_archive_installs_nothing(frozen, served, tmp_path, entries):
    bad = make_zip(tmp_path / "bad.zip", entries)
    with pytest.raises(self_update.UpdateError):
        rt.install_from_zip(bad, VERSION)
    assert not rt.runtime_dir(VERSION).exists()
    assert root_entries() == []
    assert not list(tmp_path.rglob("evil.txt"))  # nothing escaped the target folder

    served.src = bad
    assert rt.ensure_runtime(VERSION) is False
    assert root_entries() == []


# --- install_from_zip / cleanup ---------------------------------------------

def test_install_replaces_half_finished_folder(frozen, tmp_path):
    stale = make_runtime(complete=False)
    (stale / "junk.dll").write_bytes(b"half")
    rt.install_from_zip(make_zip(tmp_path / "cli.zip", {"dr.exe": PAYLOAD}), VERSION)
    assert not (stale / "junk.dll").exists()
    assert (stale / "dr.exe").read_bytes() == PAYLOAD
    assert (stale / rt.DONE_MARKER).is_file()
    assert root_entries() == [VERSION]


def test_install_keeps_already_complete_folder(frozen, tmp_path):
    done = make_runtime()
    rt.install_from_zip(make_zip(tmp_path / "cli.zip", {"dr.exe": PAYLOAD}), VERSION)
    assert (done / "dr.exe").read_bytes() == b"dr"  # installed meanwhile by another process: untouched
    assert root_entries() == [VERSION]


def test_remove_stale_runtimes_keeps_current_only(frozen):
    rt.remove_stale_runtimes(VERSION)  # no runtime/ folder yet: no-op
    make_runtime("0.1.4")
    current = make_runtime()
    old_tmp = rt.runtime_root() / ".tmp-0.1.4-ab12"
    old_tmp.mkdir()
    old_zip = rt.runtime_root() / ".download-0.1.4-ab12.zip"
    old_zip.write_bytes(b"x")
    for entry in (old_tmp, old_zip):
        os.utime(entry, (1, 1))  # long ago: abandoned
    fresh = rt.runtime_root() / ".download-0.1.6-cd34.zip"
    fresh.write_bytes(b"x")  # another daemon may be downloading right now
    rt.remove_stale_runtimes(VERSION)
    assert root_entries() == sorted([VERSION, fresh.name])
    assert (current / "dr.exe").is_file()


def test_remove_stale_runtimes_skips_folder_in_use(frozen, monkeypatch):
    old = make_runtime("0.1.4")
    real_rename = Path.rename

    def rename(self, target):
        if self == old:
            raise PermissionError(13, "in use", str(self))  # an old dr.exe still runs from it
        return real_rename(self, target)

    monkeypatch.setattr(Path, "rename", rename)
    rt.remove_stale_runtimes(VERSION)
    assert (old / "dr.exe").is_file()  # left whole, not half deleted


# --- shim, hook command, dr_command -------------------------------------------

def test_shim_body_depends_only_on_version(frozen):
    folder = rt.runtime_dir()
    expected = (f'@if not exist "{folder / rt.DONE_MARKER}" goto drover\r\n'
                f'@"{folder / "dr.exe"}" %*\r\n@exit /b %errorlevel%\r\n'
                f':drover\r\n@"{frozen}" %*\r\n')
    assert self_command.shim_body() == expected
    make_runtime()
    assert self_command.shim_body() == expected  # unchanged once installed: never rewritten under a running cmd


def test_shim_file_bytes_match_body(frozen):
    shims = self_command._dr_shim_dir()
    assert (shims / "dr.cmd").read_bytes() == self_command.shim_body().encode("utf-8")


@pytest.mark.skipif(sys.platform != "win32", reason="runs the shim with cmd.exe")
@pytest.mark.parametrize("installed", [True, False])
def test_shim_runs_target_and_keeps_exit_code(frozen, installed):
    """dr.exe and drover.exe are copies of cmd.exe here, so `dr /c exit 7` must come back as exit code 7."""
    import subprocess

    cmd_exe = Path(os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"))
    shutil.copyfile(cmd_exe, frozen)
    if installed:
        folder = make_runtime()
        shutil.copyfile(cmd_exe, folder / "dr.exe")
    shims = self_command._dr_shim_dir()
    result = subprocess.run(["cmd", "/c", str(shims / "dr.cmd"), "/c", "exit", "7"], check=False, capture_output=True)
    assert result.returncode == 7


def test_runtime_dr_exe_runs_daemon_through_owner(tmp_path, monkeypatch):
    """Inside the runtime dr.exe, `dr_command()` (daemon start, autostart) is the drover.exe in `.complete`."""
    owner = tmp_path / "drover.exe"
    owner.write_bytes(b"MZ")
    folder = make_runtime()
    (folder / rt.DONE_MARKER).write_text(str(owner), encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setattr(sys, "executable", str(folder / "dr.exe"))
    monkeypatch.setattr(sys, "_MEIPASS", str(folder / "_internal"), raising=False)
    assert self_command.is_single_exe() is False
    assert self_command.dr_command() == [str(owner)]


def test_hook_command_uses_forward_slashes_plain_then_runtime(frozen):
    exe = str(frozen).replace("\\", "/")
    assert claude_subagent_hooks.hook_command() == f'"{exe}" hook claude'
    fast = str(make_runtime() / "dr.exe").replace("\\", "/")
    assert claude_subagent_hooks.hook_command() == f'"{fast}" hook claude'
