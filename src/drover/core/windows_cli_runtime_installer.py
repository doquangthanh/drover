"""Fast `dr` on Windows: an unpacked (PyInstaller onedir) dr.exe next to the single-file drover.exe.

drover.exe is a onefile build: every `dr` call agents make starts it again (~0.4 s). Every release also ships
drover-cli-windows-x64.zip (a onedir dr.exe, ~0.2 s). The daemon installs it once per version into
<state>/runtime/<version>/ in the background. The `dr` shim checks for it on every call (see
`self_command.shim_body`), so nothing has to be rewritten once it appears. Anything missing or failing just
leaves today's behaviour (drover.exe) in place.

The `.complete` marker is written last and holds the path of the drover.exe that installed it: the runtime
dr.exe uses that path to start the daemon or the window (`self_command.dr_command`), never itself.
"""

from __future__ import annotations

import logging
import re
import secrets
import shutil
import sys
import time
import zipfile
from pathlib import Path, PurePosixPath

from drover import __version__
from drover.app_paths import state_dir
from drover.self_command import is_single_exe

log = logging.getLogger(__name__)

ZIP_NAME = "drover-cli-windows-x64.zip"
DONE_MARKER = ".complete"
TEMP_PREFIXES = (".tmp-", ".download-", ".del-")
TEMP_MAX_AGE_S = 600  # younger temp entries may belong to another daemon's install in progress
RENAME_TRIES = 5  # antivirus often holds a freshly extracted exe open for a moment


def runtime_root() -> Path:
    return state_dir() / "runtime"


def runtime_dir(version: str = __version__) -> Path:
    return runtime_root() / version


def runtime_dr_exe(version: str = __version__) -> Path | None:
    """dr.exe of the installed runtime for `version`, or None. Cheap: two stat calls."""
    folder = runtime_dir(version)
    exe = folder / "dr.exe"
    return exe if exe.is_file() and (folder / DONE_MARKER).is_file() else None


def _is_release_version(version: str) -> bool:
    """Only tagged releases ('0.1.19') have a matching asset on GitHub; dev builds skip the download."""
    return re.fullmatch(r"\d+(\.\d+)*", version) is not None


def _check_zip(archive: Path) -> None:
    """Refuse anything that is not a real CLI bundle or would write outside the target folder (zip-slip)."""
    from drover.core.self_update import MIN_EXE_BYTES, UpdateError

    if archive.stat().st_size < MIN_EXE_BYTES or not zipfile.is_zipfile(archive):
        raise UpdateError("downloaded file is not a drover CLI bundle")
    with zipfile.ZipFile(archive) as zf:
        names = zf.namelist()
    for name in names:
        path = PurePosixPath(name.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or ":" in name:
            raise UpdateError(f"unsafe path in archive: {name}")
    if "dr.exe" not in names:
        raise UpdateError("archive has no dr.exe at its top level")


def _write_marker(folder: Path) -> None:
    (folder / DONE_MARKER).write_text(sys.executable, encoding="utf-8")


def _rename_with_retry(src: Path, dst: Path) -> None:
    for attempt in range(RENAME_TRIES):
        try:
            src.rename(dst)
            return
        except FileExistsError:
            raise
        except PermissionError:
            if attempt == RENAME_TRIES - 1:
                raise
            time.sleep(0.5)


def install_from_zip(archive: Path, version: str = __version__) -> Path:
    """Extract a checked archive into runtime/<version>/ via a temp folder + rename (atomic on one volume)."""
    _check_zip(archive)
    target = runtime_dir(version)
    tmp = runtime_root() / f".tmp-{version}-{secrets.token_hex(4)}"
    try:
        with zipfile.ZipFile(archive) as zf:
            zf.extractall(tmp)
        _write_marker(tmp)
        if target.exists() and not (target / DONE_MARKER).is_file():
            shutil.rmtree(target, ignore_errors=True)  # half-finished earlier attempt
        if not target.exists():
            try:
                _rename_with_retry(tmp, target)
            except FileExistsError:
                pass  # another daemon installed it meanwhile: fine if it is complete (checked below)
        if runtime_dr_exe(version) is None:
            raise OSError(f"could not move the CLI runtime into {target}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)  # gone after a successful rename; leftovers otherwise
    return target


def ensure_runtime(version: str = __version__) -> bool:
    """Blocking (run off the event loop): download + install this version's runtime if needed.

    True when the runtime is usable afterwards. Never raises: on any failure drover.exe keeps serving `dr`.
    """
    if not is_single_exe() or not _is_release_version(version):
        return False
    installed = runtime_dr_exe(version)
    if installed is not None:
        marker = installed.parent / DONE_MARKER
        if marker.read_text(encoding="utf-8", errors="replace") != sys.executable:
            _write_marker(installed.parent)  # drover.exe was moved: point the runtime at its new place
        return True
    from drover.core.self_update import REPO, download

    root = runtime_root()
    archive = root / f".download-{version}-{secrets.token_hex(4)}.zip"
    try:
        root.mkdir(parents=True, exist_ok=True)
        download(f"https://github.com/{REPO}/releases/download/v{version}/{ZIP_NAME}", archive)
        install_from_zip(archive, version)
    except Exception as exc:  # noqa: BLE001 - optional speed-up, never fatal
        log.info("fast dr runtime not installed (%s); dr keeps using drover.exe", exc)
        return False
    finally:
        archive.unlink(missing_ok=True)
    log.info("fast dr runtime installed at %s", runtime_dir(version))
    return True


def _is_fresh_temp(entry: Path) -> bool:
    try:
        return entry.name.startswith(TEMP_PREFIXES) and time.time() - entry.stat().st_mtime < TEMP_MAX_AGE_S
    except OSError:
        return False


def remove_stale_runtimes(version: str = __version__) -> None:
    """Delete runtime folders of other versions and old temp files (best effort).

    A folder is renamed before it is deleted: if an old dr.exe still runs from it, the rename fails and the
    folder is left whole for the next start, instead of being half deleted under the running program.
    """
    root = runtime_root()
    if not root.is_dir():
        return
    for entry in root.iterdir():
        if entry.name == version or _is_fresh_temp(entry):
            continue
        if not entry.is_dir():
            entry.unlink(missing_ok=True)
            continue
        doomed = entry if entry.name.startswith(".del-") else root / f".del-{entry.name}-{secrets.token_hex(4)}"
        try:
            if doomed != entry:
                entry.rename(doomed)
        except OSError:
            continue  # still in use
        shutil.rmtree(doomed, ignore_errors=True)


def install_in_background() -> None:
    """Daemon start-up: clean old versions and install the current one (the shim picks it up by itself)."""
    if not is_single_exe():
        return
    import threading

    def run() -> None:
        try:
            remove_stale_runtimes()
            ensure_runtime()
        except Exception:  # background helper must never take the daemon down
            log.exception("fast dr runtime setup failed")

    threading.Thread(target=run, name="dr-runtime-install", daemon=True).start()
