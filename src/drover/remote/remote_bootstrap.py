"""Get a drover daemon running on a remote machine and learn its port + token."""

from __future__ import annotations

import json
import logging
import shlex

log = logging.getLogger(__name__)

def sh(script: str) -> str:
    """Run `script` in a login shell, quoted once and correctly."""
    return "sh -lc " + shlex.quote(script)


# Prefer the uv-tool install, and skip any `dr` that is not drover's (another tool of that name
# on PATH would otherwise shadow drover and never trigger an install).
ENSURE_CMD = sh('for c in "$HOME/.local/bin/dr" dr; do '
                'command -v "$c" >/dev/null 2>&1 && "$c" server --help >/dev/null 2>&1 '
                '&& exec "$c" server ensure --json; done; exit 127')
UV = 'UV=$(command -v uv || echo "$HOME/.local/bin/uv"); '


class BootstrapError(Exception):
    pass


async def ensure_remote_daemon(conn) -> dict:
    """Run `dr server ensure --json` remotely. Returns {"port", "token", "version"}."""
    result = await conn.run(ENSURE_CMD, check=False, timeout=60)
    if result.exit_status == 127:
        raise BootstrapError("dr is not installed on this machine — use 'Install dr there'")
    if result.exit_status != 0:
        raise BootstrapError((result.stderr or result.stdout or "remote dr failed").strip()[:300])
    try:
        info = json.loads(str(result.stdout).strip().splitlines()[-1])
        return {"port": int(info["port"]), "token": str(info["token"]), "version": info.get("version", "")}
    except (ValueError, KeyError, IndexError) as exc:
        raise BootstrapError(f"unexpected reply from remote dr: {str(result.stdout)[:200]}") from exc


async def install_dr(conn, wheel_path: str | None, progress) -> None:
    """Install uv (if missing) and the dr wheel on a Linux/macOS remote."""
    progress("Checking for uv")
    has_uv = await conn.run(sh('command -v uv || test -x "$HOME/.local/bin/uv"'), check=False)
    if has_uv.exit_status != 0:
        progress("Installing uv")
        res = await conn.run(sh("curl -LsSf https://astral.sh/uv/install.sh | sh"), check=False, timeout=300)
        if res.exit_status != 0:
            raise BootstrapError("could not install uv: " + str(res.stderr)[:200])
    if not wheel_path:
        raise BootstrapError("no local drover wheel to upload; run `uv build --wheel` in the drover repo first")
    progress("Uploading drover")
    # Private, unpredictable upload dir (mktemp -d is 0700): nobody else can swap the wheel.
    tmp = await conn.run(sh("mktemp -d"), check=False)
    remote_dir = str(tmp.stdout).strip()
    if tmp.exit_status != 0 or not remote_dir.startswith("/"):
        raise BootstrapError("could not create a temp folder on the remote machine")
    remote_wheel = remote_dir + "/" + wheel_path.replace("\\", "/").rsplit("/", 1)[-1]
    async with conn.start_sftp_client() as sftp:
        await sftp.put(wheel_path, remote_wheel)
    progress("Installing drover")
    script = UV + f'"$UV" tool install --force {shlex.quote(remote_wheel)}; rc=$?; rm -rf {shlex.quote(remote_dir)}; exit $rc'
    res = await conn.run(sh(script), check=False, timeout=600)
    if res.exit_status != 0:
        raise BootstrapError("install failed: " + str(res.stderr or res.stdout)[:300])
