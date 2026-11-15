"""Settings: deep merge, first-run files, user overrides, hot reload, bad TOML handling."""

from __future__ import annotations

import os
from pathlib import Path

from drover.config.settings_loader import SettingsStore, deep_merge, read_toml


def _settings_path() -> Path:
    return Path(os.environ["DROVER_CONFIG_DIR"]) / "settings.toml"


def test_deep_merge_keeps_untouched_nested_keys():
    base = {"notify": {"blocked": ["toast"], "quiet_hours": ""}, "theme": "dark"}
    merged = deep_merge(base, {"notify": {"quiet_hours": "23:00-07:00"}})
    assert merged == {"notify": {"blocked": ["toast"], "quiet_hours": "23:00-07:00"}, "theme": "dark"}


def test_deep_merge_replaces_lists_instead_of_extending():
    merged = deep_merge({"notify": {"blocked": ["toast", "sound"]}}, {"notify": {"blocked": ["desktop"]}})
    assert merged["notify"]["blocked"] == ["desktop"]


def test_deep_merge_scalar_over_dict_and_adds_new_keys():
    merged = deep_merge({"agents": {"claude": {"command": "claude"}}}, {"agents": "off", "new": 1})
    assert merged == {"agents": "off", "new": 1}


def test_deep_merge_does_not_mutate_inputs():
    base, override = {"a": {"b": 1}}, {"a": {"c": 2}}
    deep_merge(base, override)
    assert base == {"a": {"b": 1}}
    assert override == {"a": {"c": 2}}


def test_read_toml_missing_or_broken_file_is_empty(tmp_path):
    assert read_toml(tmp_path / "nope.toml") == {}
    broken = tmp_path / "broken.toml"
    broken.write_text("this = = bad", encoding="utf-8")
    assert read_toml(broken) == {}


def test_first_run_writes_default_files_and_defaults_apply():
    store = SettingsStore()
    assert _settings_path().exists()
    assert (_settings_path().parent / "AGENTS.md").exists()
    assert store.get("orchestration.max_panes") == 12
    assert store.get("notify.blocked") == ["toast", "desktop", "sound"]
    assert store.errors == []


def test_user_values_merge_over_defaults():
    _settings_path().write_text('[notify]\nquiet_hours = "23:00-07:00"\n', encoding="utf-8")
    store = SettingsStore()
    assert store.get("notify.quiet_hours") == "23:00-07:00"
    assert store.get("notify.done") == ["toast", "desktop"]
    assert store.get("theme") == "dark"


def test_get_returns_default_for_missing_or_non_dict_path():
    store = SettingsStore()
    assert store.get("no.such.key", "fallback") == "fallback"
    assert store.get("theme.deeper", "x") == "x"


def test_reload_happens_only_when_file_changes():
    store = SettingsStore()
    assert store.reload_if_changed() is False
    _settings_path().write_text("scrollback = 100\n", encoding="utf-8")
    future = _settings_path().stat().st_mtime + 10
    os.utime(_settings_path(), (future, future))
    assert store.reload_if_changed() is True
    assert store.get("scrollback") == 100


def test_invalid_toml_keeps_previous_settings_and_reports_error():
    _settings_path().write_text("scrollback = 100\n", encoding="utf-8")
    store = SettingsStore()
    _settings_path().write_text("scrollback = = 1\n", encoding="utf-8")
    future = _settings_path().stat().st_mtime + 10
    os.utime(_settings_path(), (future, future))
    assert store.reload_if_changed() is True
    assert store.errors and store.errors[0].startswith("settings.toml")
    assert store.get("scrollback") == 100
