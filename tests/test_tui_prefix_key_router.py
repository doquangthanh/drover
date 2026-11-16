from drover.tui.prefix_key_router import PrefixKeyRouter, literal_prefix, to_textual_key


def test_prefix_then_action():
    r = PrefixKeyRouter("C-a")
    assert r.handle("ctrl+a", None, 0) == ("armed", "")
    assert r.handle("z", "z", 0.5) == ("action", "zoom")
    assert not r.armed


def test_symbols_use_the_character():
    r = PrefixKeyRouter("C-a")
    r.handle("ctrl+a", None, 0)
    assert r.handle("percent_sign", "%", 0.1) == ("action", "split_right")
    r.handle("ctrl+a", None, 1)
    assert r.handle("quotation_mark", '"', 1.1) == ("action", "split_down")


def test_double_prefix_sends_literal():
    r = PrefixKeyRouter("C-a")
    r.handle("ctrl+a", None, 0)
    assert r.handle("ctrl+a", None, 0.2) == ("literal", "\x01")


def test_timeout_disarms_and_key_goes_to_pane():
    r = PrefixKeyRouter("C-a")
    r.handle("ctrl+a", None, 0)
    assert r.handle("z", "z", 5) is None
    assert not r.armed


def test_unknown_second_key_cancels_and_normal_keys_pass():
    r = PrefixKeyRouter("C-a")
    assert r.handle("e", "e", 0) is None
    r.handle("ctrl+a", None, 1)
    assert r.handle("w", "w", 1.1) == ("cancel", "")


def test_custom_prefix_and_tab_numbers():
    r = PrefixKeyRouter("C-b")
    r.handle("ctrl+b", None, 0)
    assert r.handle("3", "3", 0.1) == ("action", "goto_tab_3")
    assert to_textual_key("C-b") == "ctrl+b" and literal_prefix("C-b") == "\x02"
