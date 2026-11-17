"""The font the user's own terminal uses, so Drover's terminals look the same by default, and the installed
monospace fonts the Settings picker offers.

Linux (GNOME): the default GNOME Terminal profile's font, or the desktop's monospace font when that profile follows
the system. Elsewhere, or when gsettings is missing, nothing is found and the UI keeps the browser's monospace.
"""

from __future__ import annotations

import functools
import re
import shutil
import subprocess
import sys

_PROFILE_SCHEMA = "org.gnome.Terminal.Legacy.Profile:/org/gnome/terminal/legacy/profiles:/:{uuid}/"
_SIZE_RE = re.compile(r"^(?P<family>.+?)\s+(?P<size>\d+(?:\.\d+)?)$")


def _gsettings(schema: str, key: str) -> str | None:
    try:
        out = subprocess.run(
            ["gsettings", "get", schema, key], check=False, capture_output=True, text=True, timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip().strip("'\"") or None


def parse_pango_font(desc: str) -> tuple[str, float | None]:
    """'Ubuntu Mono 13' -> ('Ubuntu Mono', 13.0); 'Monospace' -> ('Monospace', None)."""
    match = _SIZE_RE.match(desc.strip())
    if not match:
        return desc.strip(), None
    return match.group("family"), float(match.group("size"))


@functools.lru_cache(maxsize=1)
def system_terminal_font() -> tuple[str, float | None] | None:
    """(family, size in points or None), or None when it cannot be found. Cached: gsettings runs once."""
    if sys.platform != "linux" or not shutil.which("gsettings"):
        return None
    desc = None
    uuid = _gsettings("org.gnome.Terminal.ProfilesList", "default")
    if uuid:
        schema = _PROFILE_SCHEMA.format(uuid=uuid)
        if _gsettings(schema, "use-system-font") == "false":
            desc = _gsettings(schema, "font")
    desc = desc or _gsettings("org.gnome.desktop.interface", "monospace-font-name")
    return parse_pango_font(desc) if desc else None


def default_terminal_font() -> dict:
    """{family, size in CSS px} of the system terminal; empty / 0 when unknown.

    GNOME sizes are points: 1pt = 96/72 px, so 'Ubuntu Mono 13' becomes 17 px, the size GNOME Terminal draws.
    """
    family, pt = system_terminal_font() or ("", None)
    return {"family": family, "size": round(pt * 96 / 72) if pt else 0}


@functools.lru_cache(maxsize=1)
def installed_monospace_fonts() -> tuple[str, ...]:
    """Monospace font families from fontconfig (Linux/macOS with fc-list); empty elsewhere. Cached."""
    if not shutil.which("fc-list"):
        return ()
    try:
        out = subprocess.run(
            ["fc-list", ":spacing=mono", "family"], check=False, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ()
    names = {line.split(",")[0].strip() for line in out.stdout.splitlines()}
    return tuple(sorted(n for n in names if n and "emoji" not in n.lower()))
