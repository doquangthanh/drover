"""Remote id translation: prefix on the way in, strip on the way out, round trip."""

from __future__ import annotations

import copy

from herd.remote.id_prefixing import prefix_ids, strip_ids, tag_machine

SNAPSHOT = {
    "spaces": [{"id": "s1", "name": "repo", "cwd": "C:/repo"}],
    "tabs": [{
        "id": "t1", "space_id": "s1", "focused": "%3",
        "layout": {"split": "row", "ratio": 0.5, "a": {"pane": "%3"}, "b": {"pane": "%4"}},
    }],
    "panes": [{"id": "%3", "name": "claude", "tab_id": "t1", "space_id": "s1", "parent": None, "state": "idle"}],
}


def test_prefix_adds_alias_to_id_fields_only():
    out = prefix_ids(copy.deepcopy(SNAPSHOT), "vps")
    assert out["spaces"][0]["id"] == "vps:s1"
    assert out["tabs"][0]["space_id"] == "vps:s1"
    assert out["tabs"][0]["focused"] == "vps:%3"
    assert out["tabs"][0]["layout"]["a"]["pane"] == "vps:%3"
    assert out["panes"][0]["parent"] is None
    assert out["panes"][0]["name"] == "claude"
    assert out["panes"][0]["state"] == "idle"
    assert out["spaces"][0]["cwd"] == "C:/repo"


def test_already_prefixed_or_empty_ids_are_left_alone():
    assert prefix_ids({"id": "other:%9"}, "vps") == {"id": "other:%9"}
    assert prefix_ids({"parent": ""}, "vps") == {"parent": ""}


def test_strip_removes_alias_and_machine_key():
    tagged = {"id": "vps:%3", "machine": "vps", "name": "keep-me"}
    assert strip_ids(tagged, "vps") == {"id": "%3", "name": "keep-me"}


def test_strip_leaves_user_text_that_starts_with_alias():
    # Review L2: a prompt like "vps: deploy now" must reach the agent unchanged.
    msg = {"t": "rpc", "params": {"pane": "vps:%3", "text": "vps: deploy now", "panes": ["vps:%1", "vps:%2"]}}
    assert strip_ids(msg, "vps") == {"t": "rpc", "params": {"pane": "%3", "text": "vps: deploy now",
                                                            "panes": ["%1", "%2"]}}


def test_strip_handles_layout_leaves():
    layout = {"split": "row", "ratio": 0.5, "a": {"pane": "vps:%1"}, "b": {"pane": "vps:%2"}}
    assert strip_ids({"tab": "vps:t1", "layout": layout}, "vps") == {
        "tab": "t1", "layout": {"split": "row", "ratio": 0.5, "a": {"pane": "%1"}, "b": {"pane": "%2"}}}


def test_prefix_then_strip_is_identity():
    original = copy.deepcopy(SNAPSHOT)
    assert strip_ids(prefix_ids(copy.deepcopy(SNAPSHOT), "vps"), "vps") == original


def test_tag_machine_marks_panes_spaces_and_stopped():
    snapshot = {"panes": [{"id": "%1"}], "spaces": [{"id": "s1"}], "stopped": [{"id": "%2"}], "tabs": []}
    tagged = tag_machine(snapshot, "lab")
    assert tagged["panes"][0]["machine"] == "lab"
    assert tagged["spaces"][0]["machine"] == "lab"
    assert tagged["stopped"][0]["machine"] == "lab"
