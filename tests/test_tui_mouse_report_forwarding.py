"""Clicks and wheel reach the app in a pane once it turns mouse reporting on (Claude's "Jump to bottom" button)."""

from __future__ import annotations

from textual import events
from textual.app import App, ComposeResult

from drover.tui.terminal_mouse_report_bytes import WHEEL_UP, button_code, mouse_report
from drover.tui.terminal_pane_view import TerminalPaneView

MOUSE_ON = "\x1b[?1000h\x1b[?1006h"  # click reporting, SGR encoding
ALT_SCREEN = "\x1b[?1049h"


def test_sgr_and_legacy_encoding():
    assert mouse_report(0, 4, 2, pressed=True, sgr=True) == "\x1b[<0;5;3M"
    assert mouse_report(0, 4, 2, pressed=False, sgr=True) == "\x1b[<0;5;3m"
    assert mouse_report(WHEEL_UP, 0, 0, pressed=True, sgr=True) == "\x1b[<64;1;1M"
    assert mouse_report(0, 4, 2, pressed=True, sgr=False) == "\x1b[M" + chr(32) + chr(37) + chr(35)
    assert mouse_report(0, 4, 2, pressed=False, sgr=False) == "\x1b[M" + chr(35) + chr(37) + chr(35)
    assert mouse_report(0, 300, 2, pressed=True, sgr=False) == ""  # legacy cannot address that cell


def test_button_codes_and_modifiers():
    assert [button_code(b) for b in (1, 2, 3)] == [0, 1, 2]
    assert button_code(1, shift=True, ctrl=True) == 20
    assert button_code(9) is None


class PaneApp(App):
    def __init__(self) -> None:
        super().__init__()
        self.sent: list[str] = []

    def compose(self) -> ComposeResult:
        yield TerminalPaneView(self.sent.append, lambda cols, rows: None)


def wheel(pane: TerminalPaneView, up: bool, x: int = 5, y: int = 2) -> None:
    """Post a real wheel event at pane-content cell (x, y), as the driver would."""
    region = pane.content_region
    cls = events.MouseScrollUp if up else events.MouseScrollDown
    pane.post_message(cls(pane, x, y, 0, 0, 0, False, False, False, region.x + x, region.y + y))


async def test_click_is_forwarded_only_when_the_app_asked_for_the_mouse():
    app = PaneApp()
    async with app.run_test(size=(80, 24)) as pilot:
        pane = app.query_one(TerminalPaneView)
        await pilot.click(TerminalPaneView, offset=(5, 2))
        assert not any(s.startswith("\x1b[<") for s in app.sent)  # mouse reporting off: nothing sent

        pane.feed(ALT_SCREEN + MOUSE_ON)
        await pilot.click(TerminalPaneView, offset=(5, 2))
        assert "\x1b[<0;6;3M" in app.sent and "\x1b[<0;6;3m" in app.sent


async def test_legacy_click_encoding_when_sgr_is_off():
    app = PaneApp()
    async with app.run_test(size=(80, 24)) as pilot:
        pane = app.query_one(TerminalPaneView)
        pane.feed("\x1b[?1000h")  # no ?1006: X10 bytes
        await pilot.click(TerminalPaneView, offset=(5, 2))
        assert "\x1b[M" + chr(32) + chr(38) + chr(35) in app.sent  # press: button 0, x 5+1, y 2+1
        assert "\x1b[M" + chr(35) + chr(38) + chr(35) in app.sent  # release: button 3 (code 3 + 32)


async def test_wheel_is_forwarded_as_sgr_64_and_65_when_mouse_mode_is_on():
    app = PaneApp()
    async with app.run_test(size=(80, 24)) as pilot:
        pane = app.query_one(TerminalPaneView)
        pane.feed(ALT_SCREEN + MOUSE_ON)
        wheel(pane, up=True)
        wheel(pane, up=False)
        await pilot.pause()
        assert "\x1b[<64;6;3M" in app.sent and "\x1b[<65;6;3M" in app.sent
        assert not any(s.startswith(("\x1b[A", "\x1b[B")) for s in app.sent)  # not arrows


async def test_wheel_sends_arrows_in_alt_screen_without_mouse_mode():
    app = PaneApp()
    async with app.run_test(size=(80, 24)) as pilot:
        pane = app.query_one(TerminalPaneView)
        pane.feed(ALT_SCREEN)
        wheel(pane, up=True)
        await pilot.pause()
        assert app.sent == ["\x1b[A" * 3]
        app.sent.clear()
        pane.feed("\x1b[?1h")  # DECCKM: application cursor keys
        wheel(pane, up=False)
        await pilot.pause()
        assert app.sent == ["\x1bOB" * 3]


async def test_wheel_scrolls_local_scrollback_on_main_screen():
    app = PaneApp()
    async with app.run_test(size=(80, 24)) as pilot:
        pane = app.query_one(TerminalPaneView)
        pane.feed("".join(f"line {i}\r\n" for i in range(100)))  # fills history, main screen
        wheel(pane, up=True)
        await pilot.pause()
        assert app.sent == []
        assert pane.emulator.scroll > 0
        wheel(pane, up=False)
        await pilot.pause()
        assert app.sent == []


async def test_clicks_are_not_forwarded_in_scroll_mode():
    app = PaneApp()
    async with app.run_test(size=(80, 24)) as pilot:
        pane = app.query_one(TerminalPaneView)
        pane.feed(ALT_SCREEN + MOUSE_ON)
        pane.set_scroll_mode(True)  # copy mode owns the mouse
        await pilot.click(TerminalPaneView, offset=(5, 2))
        assert not any(s.startswith("\x1b[<") for s in app.sent)


class SplitApp(PaneApp):
    CSS = "#other { width: 20; }"  # the pane keeps the other 60 columns

    def compose(self) -> ComposeResult:
        from textual.containers import Horizontal
        from textual.widgets import Static

        with Horizontal():
            yield TerminalPaneView(self.sent.append, lambda cols, rows: None, id="pane")
            yield Static("other", id="other")


async def test_release_over_another_widget_still_reaches_the_app():
    app = SplitApp()
    async with app.run_test(size=(80, 24)) as pilot:
        pane = app.query_one(TerminalPaneView)
        pane.feed(ALT_SCREEN + MOUSE_ON)
        await pilot.mouse_down("#pane", offset=(5, 2))
        await pilot.mouse_up("#other", offset=(3, 2))  # dragged out of the pane before letting go
        right = pane.emulator.cols  # clamped to the last column (1-based)
        assert "\x1b[<0;6;3M" in app.sent and f"\x1b[<0;{right};3m" in app.sent
        assert app.mouse_captured is None
