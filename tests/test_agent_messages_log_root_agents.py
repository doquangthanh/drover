"""Agent tree Flow board data: agents you start (no parent) also get spawn / done / blocked events."""

from drover.core.agent_messages_log import AgentMessagesLog


def test_state_events_go_to_parent_or_you():
    log = AgentMessagesLog()
    log.add("spawn", None, "root")
    log.add("spawn", "root", "helper")
    assert log.add_state("helper", "root", "done").target == "root"
    assert log.add_state("root", None, "blocked").target is None
    assert log.add_state("root", "", "done").target is None
    assert log.add_state("root", None, "working") is None
    assert [(m.kind, m.source, m.target) for m in log.items] == [
        ("spawn", None, "root"), ("spawn", "root", "helper"), ("done", "helper", "root"),
        ("blocked", "root", None), ("done", "root", None)]


def test_exit_is_reported_with_its_code():
    log = AgentMessagesLog()
    m = log.add_state("helper", "root", "exited", "exit code 0")
    assert (m.kind, m.source, m.target, m.text) == ("exited", "helper", "root", "exit code 0")


def test_long_text_is_cut():
    m = AgentMessagesLog().add("send", "a", "b", "x" * 2000)
    assert len(m.text) == 501 and m.text.endswith("…")


def test_for_tree_includes_events_with_you():
    log = AgentMessagesLog()
    log.add("spawn", None, "root")
    log.add_state("root", None, "done")
    log.add("spawn", None, "other")
    assert [m["kind"] for m in log.for_tree({"root"})] == ["spawn", "done"]
