"""Sidebar tree: spaces > tabs > panes with an agent-state glyph. Updated in place (keeps expansion and cursor)."""

from __future__ import annotations

from rich.text import Text
from textual.message import Message
from textual.widgets import Tree
from textual.widgets.tree import TreeNode

from drover.tui.tui_state_helpers import panes_of, state_glyph, tab_state, tabs_of


class TabSelected(Message):
    def __init__(self, tab_id: str) -> None:
        super().__init__()
        self.tab_id = tab_id


class PaneSelected(Message):
    def __init__(self, pane_id: str, tab_id: str) -> None:
        super().__init__()
        self.pane_id, self.tab_id = pane_id, tab_id


def _label(state: str, name: str, bold: bool = False) -> Text:
    glyph, style = state_glyph(state)
    text = Text()
    text.append(glyph + " ", style=style)
    text.append(name, style="bold" if bold else "")
    return text


class WorkspaceSidebar(Tree[str]):
    def __init__(self, **kwargs) -> None:
        super().__init__("drover", **kwargs)
        self.show_root = False
        self.guide_depth = 3
        self._by_id: dict[str, TreeNode[str]] = {}

    def rebuild(self, state: dict) -> None:
        """Bring the tree in line with `state`: add new nodes, relabel, drop gone ones."""
        wanted: set[str] = set()
        for space in state.get("spaces", []):
            sid = space["id"]
            wanted.add(sid)
            node = self._node(sid, self.root, space["name"], allow_expand=True)
            node.set_label(Text(space["name"], style="bold"))
            for tab in tabs_of(state, sid):
                tid = tab["id"]
                wanted.add(tid)
                tnode = self._node(tid, node, tab["name"], allow_expand=True)
                tnode.set_label(_label(tab_state(state, tab), tab["name"]))
                for pane in panes_of(state, tab):
                    wanted.add(pane["id"])
                    pnode = self._node(pane["id"], tnode, pane["name"], allow_expand=False)
                    pnode.set_label(_label(pane["state"], pane["name"] or pane["id"]))
        for gone in [i for i in self._by_id if i not in wanted]:
            self._by_id.pop(gone).remove()

    def _node(self, node_id: str, parent: TreeNode[str], label: str, allow_expand: bool) -> TreeNode[str]:
        node = self._by_id.get(node_id)
        if node is None:
            node = parent.add(label, data=node_id, allow_expand=allow_expand, expand=allow_expand)
            self._by_id[node_id] = node
        return node

    def select_id(self, node_id: str) -> None:
        node = self._by_id.get(node_id)
        if node is not None:
            self.move_cursor(node)

    def on_tree_node_selected(self, event: Tree.NodeSelected[str]) -> None:
        event.stop()
        node_id = event.node.data
        if node_id is None:
            return
        if node_id.startswith("%") or ":%" in node_id:
            tab_node = event.node.parent
            self.post_message(PaneSelected(node_id, tab_node.data if tab_node and tab_node.data else ""))
        elif node_id in self._by_id and event.node.parent is not None and event.node.parent.data is not None:
            self.post_message(TabSelected(node_id))  # a tab node (its parent is a space node)
        # a space node only expands/collapses (Tree does that itself)
