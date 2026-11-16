"""Which program holds a pane's terminal right now (Herdr-style agent detection, Linux/macOS).

The shell's terminal has one foreground process group: the program you just typed. Its process names tell
whether an agent (claude, codex, ...) runs there, and its cwd tells where the pane is. Windows has no such
notion here; every function returns None there and callers keep the terminal-title fallback.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

PROC = Path("/proc")
# Executable names that differ from the rule-set id they belong to.
ALIASES = {"claude-code": "claude", "open-code": "opencode", "opencode2": "opencode", "gemini-cli": "gemini"}
# Interpreters that run an agent as a script: the agent is the first non-option argument.
RUNTIMES = {"node", "bun", "deno", "python", "python3", "sh", "bash", "zsh", "fish"}
SCRIPT_EXTS = (".js", ".mjs", ".cjs", ".ts", ".py")


def foreground_pgid(shell_pid: int | None, tty_fd: int | None) -> int | None:
    """Foreground process group of the pane's terminal (tpgid in /proc/<pid>/stat, or tcgetpgrp)."""
    if shell_pid and PROC.is_dir():
        try:
            stat = (PROC / str(shell_pid) / "stat").read_text()
            tpgid = int(stat[stat.rindex(")") + 2:].split()[5])
            return tpgid if tpgid > 0 else None
        except (OSError, ValueError, IndexError):
            return None
    if tty_fd is not None and sys.platform != "win32":
        try:
            pgid = os.tcgetpgrp(tty_fd)
            return pgid if pgid > 0 else None
        except OSError:
            return None
    return None


def process_argv(pid: int) -> list[str]:
    if PROC.is_dir():
        try:
            raw = (PROC / str(pid) / "cmdline").read_bytes()
            argv = [a.decode("utf-8", "replace") for a in raw.split(b"\0") if a]
            if argv:
                return argv
            return [(PROC / str(pid) / "comm").read_text().strip()]  # kernel threads, zombies
        except OSError:
            return []
    try:  # macOS: no procfs
        out = subprocess.run(["ps", "-o", "command=", "-p", str(pid)], capture_output=True, text=True, timeout=1, check=False)
        return out.stdout.split()
    except (OSError, subprocess.SubprocessError):
        return []


def group_members(pgid: int) -> list[int]:
    """Every process in the group, leader first (Linux only; elsewhere just the leader)."""
    members = [pgid]
    if not PROC.is_dir():
        return members
    for entry in PROC.iterdir():
        if not entry.name.isdigit() or int(entry.name) == pgid:
            continue
        try:
            stat = (entry / "stat").read_text()
            if int(stat[stat.rindex(")") + 2:].split()[2]) == pgid:
                members.append(int(entry.name))
        except (OSError, ValueError, IndexError):
            continue
    return members


def process_cwd(pid: int) -> str | None:
    if PROC.is_dir():
        try:
            return os.readlink(PROC / str(pid) / "cwd")
        except OSError:
            return None
    try:  # macOS
        out = subprocess.run(["lsof", "-a", "-p", str(pid), "-d", "cwd", "-Fn"], capture_output=True, text=True, check=False,
                             timeout=1)
        return next((line[1:] for line in out.stdout.splitlines() if line.startswith("n/")), None)
    except (OSError, subprocess.SubprocessError):
        return None


def _base(arg: str) -> str:
    name = os.path.basename(arg).lower()
    for ext in SCRIPT_EXTS:
        if name.endswith(ext):
            return name[: -len(ext)]
    return name


def agent_kind_from_argv(argv: list[str], kinds: set[str]) -> str | None:
    """Rule-set id for a command line: `claude`, `/usr/bin/codex`, `node .../bin/claude`, `sh -c gemini`."""
    if not argv:
        return None
    names = [_base(argv[0])]
    if names[0] in RUNTIMES:
        rest = [a for a in argv[1:] if not a.startswith("-")]
        if names[0] in ("sh", "bash", "zsh", "fish") and "-c" in argv[1:]:
            rest = argv[argv.index("-c") + 1:][:1]
            rest = rest[0].split()[:1] if rest else []
        names += [_base(a) for a in rest[:1]]
    for name in names:
        kind = ALIASES.get(name, name)
        if kind in kinds and kind != "shell":
            return kind
    return None


def foreground_agent_kind(pgid: int, kinds: set[str]) -> str | None:
    """Agent running in the foreground group: the leader first, then any other member."""
    for pid in group_members(pgid):
        kind = agent_kind_from_argv(process_argv(pid), kinds)
        if kind:
            return kind
    return None


def follow_cwd(shell_pid: int | None, tty_fd: int | None) -> str | None:
    """Where the pane is now: cwd of the foreground program, else of the shell (Herdr's follow_cwd)."""
    pgid = foreground_pgid(shell_pid, tty_fd)
    for pid in (pgid, shell_pid):
        if pid:
            cwd = process_cwd(pid)
            if cwd and os.path.isdir(cwd):
                return cwd
    return None
