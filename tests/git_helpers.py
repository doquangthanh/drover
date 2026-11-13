"""Small helpers for tests that need a real git repository."""

from __future__ import annotations

import subprocess
from pathlib import Path


def run_git(cwd: str | Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)
    return result.stdout
