"""pyte colour names must map to colours Rich accepts (pyte calls ANSI yellow "brown")."""

import pytest
from rich.color import Color

from drover.tui.terminal_pane_view import rich_color


@pytest.mark.parametrize("name, expected", [
    ("default", None),
    ("brown", "yellow"),
    ("brightbrown", "bright_yellow"),
    ("brightred", "bright_red"),
    ("ff8800", "#ff8800"),
    ("green", "green"),
])
def test_rich_color_maps_pyte_names(name, expected):
    assert rich_color(name) == expected


@pytest.mark.parametrize("name", ["black", "red", "green", "brown", "blue", "magenta", "cyan", "white"])
def test_every_ansi_colour_and_bright_variant_parses_in_rich(name):
    Color.parse(rich_color(name))
    Color.parse(rich_color("bright" + name))
