"""`dr self-update <tag>` (internal): replace this install with release `tag`; nothing is restarted.

The Rust daemon on Windows runs `drover.exe self-update <tag>` for `update.apply`: swapping the running drover.exe
is Python's job (`self_update.apply_windows_exe`), restarting the daemon stays with the caller.
"""

from __future__ import annotations

import sys


def add_self_update_parser(sub) -> None:
    cmd = sub.add_parser("self-update", help="internal: replace this install with a release (Rust daemon update)")
    cmd.add_argument("tag")


def cmd_self_update(args) -> int:
    from drover.core import self_update

    try:
        self_update.apply(args.tag)
    except self_update.UpdateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0
