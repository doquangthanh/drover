"""OSC 7501 self-report parser: terminators, last-wins rule, invalid input ignored."""

from __future__ import annotations

import pytest

from drover.status.osc7501_parser import parse_osc7501

ESC = "\x1b"
BEL = "\x07"


def test_bel_terminated_report_with_extra_field():
    assert parse_osc7501(f"{ESC}]7501;state=blocked:app=my-agent{BEL}") == {"state": "blocked", "app": "my-agent"}


def test_st_terminated_report_is_parsed():
    assert parse_osc7501(f"output\r\n{ESC}]7501;state=done{ESC}\\more") == {"state": "done"}


def test_report_embedded_in_normal_output_is_found():
    chunk = "build ok\r\n" + ESC + "]7501;state=idle" + BEL + "prompt> "
    assert parse_osc7501(chunk) == {"state": "idle"}


def test_last_valid_report_in_chunk_wins():
    chunk = f"{ESC}]7501;state=working{BEL}...{ESC}]7501;state=idle{BEL}"
    assert parse_osc7501(chunk)["state"] == "idle"


def test_invalid_state_after_valid_one_is_ignored():
    chunk = f"{ESC}]7501;state=blocked{BEL}{ESC}]7501;state=exploding{BEL}"
    assert parse_osc7501(chunk) == {"state": "blocked"}


def test_whitespace_around_key_and_value_is_stripped():
    assert parse_osc7501(f"{ESC}]7501; state = working {BEL}") == {"state": "working"}


@pytest.mark.parametrize("chunk", [
    "",
    "plain text only",
    f"{ESC}]7501;state=bogus{BEL}",
    f"{ESC}]7501;app=x{BEL}",
    f"{ESC}]7501;state={BEL}",
    f"{ESC}]7501;state=idle",  # unterminated, never completed
    f"{ESC}]7502;state=idle{BEL}",  # wrong OSC number
])
def test_invalid_or_missing_reports_return_none(chunk):
    assert parse_osc7501(chunk) is None
