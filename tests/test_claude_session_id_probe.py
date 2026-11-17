"""A claude pane resumes its own conversation (`claude --resume <id>`), not the folder's newest (`--continue`)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from drover.core import status_monitor
from drover.core.claude_session_id_probe import has_transcript, resume_command, running_session_id
from drover.core.status_monitor import StatusMonitor

SID = "43095840-6fa3-4a74-8ad1-859fa07dcc6d"


def _claude_running(config: Path, pid: int, sid: str = SID, transcript: bool = True) -> None:
    (config / "sessions").mkdir(parents=True, exist_ok=True)
    (config / "sessions" / f"{pid}.json").write_text(json.dumps({"pid": pid, "sessionId": sid}), encoding="utf-8")
    if transcript:
        (config / "projects" / "-home-me-repo").mkdir(parents=True, exist_ok=True)
        (config / "projects" / "-home-me-repo" / f"{sid}.jsonl").write_text("{}\n", encoding="utf-8")


def test_session_id_from_the_first_pid_that_runs_claude(tmp_path):
    _claude_running(tmp_path, 222)
    assert running_session_id([111, 222], tmp_path) == SID
    assert running_session_id([111], tmp_path) is None


def test_odd_session_files_are_ignored(tmp_path):
    (tmp_path / "sessions").mkdir()
    (tmp_path / "sessions" / "1.json").write_text("not json", encoding="utf-8")
    (tmp_path / "sessions" / "2.json").write_text('["a list"]', encoding="utf-8")
    (tmp_path / "sessions" / "3.json").write_text('{"sessionId": "x; rm -rf ~"}', encoding="utf-8")
    assert running_session_id([1, 2, 3], tmp_path) is None


def test_transcript_must_exist_before_resume(tmp_path):
    _claude_running(tmp_path, 5, transcript=False)
    assert not has_transcript(SID, tmp_path)
    _claude_running(tmp_path, 5)
    assert has_transcript(SID, tmp_path)


def _monitor_and_pane(kind: str = "claude"):
    saves = []
    manager = SimpleNamespace(on_structure_change=lambda: saves.append(1))
    monitor = StatusMonitor.__new__(StatusMonitor)
    monitor.manager = manager
    pane = SimpleNamespace(meta=SimpleNamespace(kind=kind, resume="claude --continue"), alive=True,
                           backend=SimpleNamespace(pid=100, tty_fd=7), claude_checked_at=0.0)
    return monitor, pane, saves


def test_monitor_switches_resume_to_the_running_conversation(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(status_monitor, "foreground_pgid", lambda pid, fd: 300)
    _claude_running(tmp_path, 300)
    monitor, pane, saves = _monitor_and_pane()
    monitor.probe_claude_session(pane, now=100.0)
    assert pane.meta.resume == resume_command(SID) == f"claude --resume {SID}"
    assert saves == [1]
    monitor.probe_claude_session(pane, now=200.0)  # same conversation: nothing to save again
    assert saves == [1]


def test_monitor_keeps_continue_without_transcript_or_for_other_kinds(tmp_path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(status_monitor, "foreground_pgid", lambda pid, fd: 300)
    _claude_running(tmp_path, 300, transcript=False)
    monitor, pane, saves = _monitor_and_pane()
    monitor.probe_claude_session(pane, now=100.0)
    assert pane.meta.resume == "claude --continue" and saves == []

    _claude_running(tmp_path, 300)
    monitor, pane, saves = _monitor_and_pane(kind="codex")
    monitor.probe_claude_session(pane, now=100.0)
    assert pane.meta.resume == "claude --continue" and saves == []
