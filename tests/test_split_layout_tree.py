"""Pane layout tree: insert, remove, ratio edits, validation."""

from __future__ import annotations

import copy

import pytest

from herd.core import split_layout_tree as layout


def test_pane_ids_of_empty_tree_is_empty():
    assert layout.pane_ids(None) == []
    assert layout.pane_ids({}) == []


def test_insert_into_empty_tree_makes_single_leaf():
    assert layout.insert(None, None, "%1") == {"pane": "%1"}


def test_insert_splits_target_side_by_side_by_default():
    tree = layout.insert(layout.leaf("%1"), "%1", "%2")
    assert tree == {"split": "row", "ratio": 0.5, "a": {"pane": "%1"}, "b": {"pane": "%2"}}


def test_insert_direction_col_stacks_panes():
    tree = layout.insert(layout.leaf("%1"), "%1", "%2", direction="col")
    assert tree["split"] == "col"
    assert layout.pane_ids(tree) == ["%1", "%2"]


def test_insert_with_missing_target_splits_last_leaf():
    tree = layout.insert(layout.leaf("%1"), "%1", "%2")
    tree = layout.insert(tree, "%missing", "%3")
    assert layout.pane_ids(tree) == ["%1", "%2", "%3"]
    assert tree["b"] == {"split": "row", "ratio": 0.5, "a": {"pane": "%2"}, "b": {"pane": "%3"}}


def test_pane_ids_keep_left_to_right_order_after_nested_inserts():
    tree = layout.leaf("%1")
    tree = layout.insert(tree, "%1", "%2")
    tree = layout.insert(tree, "%2", "%3", direction="col")
    tree = layout.insert(tree, "%1", "%4")
    assert layout.pane_ids(tree) == ["%1", "%4", "%2", "%3"]


def test_insert_does_not_mutate_original_tree():
    original = layout.insert(layout.leaf("%1"), "%1", "%2")
    snapshot = copy.deepcopy(original)
    layout.insert(original, "%1", "%3")
    assert original == snapshot


def test_remove_sibling_takes_parent_place():
    tree = layout.insert(layout.leaf("%1"), "%1", "%2")
    assert layout.remove(tree, "%1") == {"pane": "%2"}
    assert layout.remove(tree, "%2") == {"pane": "%1"}


def test_remove_last_pane_returns_none():
    assert layout.remove(layout.leaf("%1"), "%1") is None
    assert layout.remove(None, "%1") is None


def test_remove_unknown_pane_keeps_tree():
    tree = layout.insert(layout.leaf("%1"), "%1", "%2")
    assert layout.remove(tree, "%9") == tree


def test_remove_from_nested_tree_collapses_only_emptied_branch():
    tree = layout.insert(layout.leaf("%1"), "%1", "%2")
    tree = layout.insert(tree, "%2", "%3", direction="col")
    tree = layout.remove(tree, "%3")
    assert tree == {"split": "row", "ratio": 0.5, "a": {"pane": "%1"}, "b": {"pane": "%2"}}


def test_set_ratio_on_root_updates_ratio():
    tree = layout.insert(layout.leaf("%1"), "%1", "%2")
    assert layout.set_ratio(tree, "", 0.3)["ratio"] == 0.3


def test_set_ratio_clamps_between_point_one_and_point_nine():
    tree = layout.insert(layout.leaf("%1"), "%1", "%2")
    assert layout.set_ratio(tree, "", 0.01)["ratio"] == 0.1
    assert layout.set_ratio(tree, "", 5)["ratio"] == 0.9


def test_set_ratio_follows_path_to_nested_split():
    tree = layout.insert(layout.leaf("%1"), "%1", "%2")
    tree = layout.insert(tree, "%2", "%3", direction="col")
    updated = layout.set_ratio(tree, "b", 0.7)
    assert updated["b"]["ratio"] == 0.7
    assert updated["ratio"] == 0.5


def test_set_ratio_on_leaf_or_empty_is_noop():
    assert layout.set_ratio(layout.leaf("%1"), "", 0.2) == {"pane": "%1"}
    assert layout.set_ratio(None, "", 0.2) is None


def test_is_valid_accepts_leaf_and_split():
    tree = layout.insert(layout.leaf("%1"), "%1", "%2")
    assert layout.is_valid(layout.leaf("%1"))
    assert layout.is_valid(tree)


@pytest.mark.parametrize("bad", [
    None,
    "x",
    [],
    {},
    {"pane": 3},
    {"split": "diag", "a": {"pane": "%1"}, "b": {"pane": "%2"}},
    {"split": "row", "a": {"pane": "%1"}},
    {"split": "row", "a": {"pane": "%1"}, "b": "oops"},
])
def test_is_valid_rejects_malformed_nodes(bad):
    assert layout.is_valid(bad) is False
