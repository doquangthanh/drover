"""Default terminal font = the system terminal's (GNOME Terminal profile, then desktop mono); font picker list."""

from __future__ import annotations

import pytest

from drover.config import system_terminal_font as stf


@pytest.fixture(autouse=True)
def _clear_cache():
    stf.system_terminal_font.cache_clear()
    stf.installed_monospace_fonts.cache_clear()
    yield
    stf.system_terminal_font.cache_clear()
    stf.installed_monospace_fonts.cache_clear()


def _fake_gsettings(monkeypatch, values: dict[tuple[str, str], str]) -> None:
    monkeypatch.setattr(stf.sys, "platform", "linux")
    monkeypatch.setattr(stf.shutil, "which", lambda _name: "/usr/bin/gsettings")
    monkeypatch.setattr(stf, "_gsettings", lambda schema, key: values.get((schema, key)))


PROFILE = stf._PROFILE_SCHEMA.format(uuid="abc")


def test_parse_pango_font():
    assert stf.parse_pango_font("Ubuntu Mono 13") == ("Ubuntu Mono", 13.0)
    assert stf.parse_pango_font("Fira Code 10.5") == ("Fira Code", 10.5)
    assert stf.parse_pango_font("Monospace") == ("Monospace", None)


def test_profile_that_follows_system_uses_desktop_monospace(monkeypatch):
    _fake_gsettings(monkeypatch, {
        ("org.gnome.Terminal.ProfilesList", "default"): "abc",
        (PROFILE, "use-system-font"): "true",
        (PROFILE, "font"): "Monospace 12",
        ("org.gnome.desktop.interface", "monospace-font-name"): "Ubuntu Mono 13",
    })
    assert stf.default_terminal_font() == {"family": "Ubuntu Mono", "size": 17}  # 13pt = 17px


def test_profile_with_its_own_font(monkeypatch):
    _fake_gsettings(monkeypatch, {
        ("org.gnome.Terminal.ProfilesList", "default"): "abc",
        (PROFILE, "use-system-font"): "false",
        (PROFILE, "font"): "JetBrains Mono 12",
        ("org.gnome.desktop.interface", "monospace-font-name"): "Ubuntu Mono 13",
    })
    assert stf.default_terminal_font() == {"family": "JetBrains Mono", "size": 16}


def test_no_gsettings_gives_empty(monkeypatch):
    monkeypatch.setattr(stf.sys, "platform", "win32")
    assert stf.default_terminal_font() == {"family": "", "size": 0}


def test_installed_monospace_fonts(monkeypatch):
    class Out:
        stdout = "Ubuntu Mono\nDejaVu Sans Mono,DejaVu Sans Mono Book\nNoto Color Emoji\nUbuntu Mono\n\n"

    monkeypatch.setattr(stf.shutil, "which", lambda _name: "/usr/bin/fc-list")
    monkeypatch.setattr(stf.subprocess, "run", lambda *a, **k: Out())
    assert stf.installed_monospace_fonts() == ("DejaVu Sans Mono", "Ubuntu Mono")


def test_no_fc_list_gives_no_fonts(monkeypatch):
    monkeypatch.setattr(stf.shutil, "which", lambda _name: None)
    assert stf.installed_monospace_fonts() == ()
