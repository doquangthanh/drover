"""Every segment a pane draws carries a real Style: Textual's monochrome filter crashes on style=None."""

from __future__ import annotations

from textual.app import App, ComposeResult

from drover.tui.terminal_pane_view import TerminalPaneView


class PaneApp(App):
    def compose(self) -> ComposeResult:
        yield TerminalPaneView(lambda data: None, lambda cols, rows: None)


async def test_blank_cursor_and_padding_segments_have_a_style():
    app = PaneApp()
    async with app.run_test(size=(40, 10)) as pilot:
        pane = app.query_one(TerminalPaneView)
        pane.feed("hi\x1b[10C")  # text, then the cursor sits past the last drawn cell
        pane.focus()
        await pilot.pause()
        for y in range(pane.size.height + 1):  # +1: a row beyond the emulator's rows
            for segment in pane.render_line(y):
                assert segment.style is not None, f"row {y}: {segment.text!r} drawn with style=None"
