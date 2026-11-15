"""SDK messages -> transcript items: streaming text, tool calls with results, interrupted turns, turn results."""

from __future__ import annotations

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    StreamEvent,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)

from drover.chat.transcript_builder import MAX_RESULT_CHARS, TranscriptBuilder, result_text


def stream(event: dict) -> StreamEvent:
    return StreamEvent(uuid="u", session_id="s", event=event, parent_tool_use_id=None)


def assistant(*blocks, parent=None) -> AssistantMessage:
    return AssistantMessage(content=list(blocks), model="m", parent_tool_use_id=parent)


def result(is_error=False, text=None) -> ResultMessage:
    return ResultMessage(subtype="success", duration_ms=1200, duration_api_ms=1000, is_error=is_error, num_turns=2,
                         session_id="s", total_cost_usd=0.01, result=text)


def test_streamed_text_grows_then_is_finalised_in_place():
    b = TranscriptBuilder()
    start = b.feed(stream({"type": "content_block_start", "index": 0, "content_block": {"type": "text"}}))
    item_id = start[0]["item"]["id"]
    assert start[0]["item"]["live"] is True
    deltas = [b.feed(stream({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": t}})) for t in ("Hel", "lo")]
    assert deltas == [[{"op": "delta", "id": item_id, "text": "Hel"}], [{"op": "delta", "id": item_id, "text": "lo"}]]
    final = b.feed(assistant(TextBlock(text="Hello")))
    assert final[0]["item"]["id"] == item_id and final[0]["item"]["text"] == "Hello" and final[0]["item"]["live"] is False
    assert len(b.items) == 1


def test_thinking_and_text_do_not_mix_up_when_both_stream():
    b = TranscriptBuilder()
    b.feed(stream({"type": "content_block_start", "index": 0, "content_block": {"type": "thinking"}}))
    b.feed(stream({"type": "content_block_start", "index": 1, "content_block": {"type": "text"}}))
    b.feed(stream({"type": "content_block_delta", "index": 1, "delta": {"text": "answer"}}))
    b.feed(stream({"type": "content_block_delta", "index": 0, "delta": {"thinking": "hmm"}}))
    b.feed(assistant(ThinkingBlock(thinking="hmm", signature="x")))
    b.feed(assistant(TextBlock(text="answer")))
    kinds = {i["kind"]: i["text"] for i in b.items.values()}
    assert kinds == {"thinking": "hmm", "text": "answer"}
    assert not any(i["live"] for i in b.items.values())


def test_message_without_streaming_still_produces_items():
    b = TranscriptBuilder()
    ops = b.feed(assistant(TextBlock(text="done")))
    assert ops[0]["item"]["kind"] == "text" and ops[0]["item"]["live"] is False


def test_tool_call_then_result_updates_the_same_item():
    b = TranscriptBuilder()
    b.feed(assistant(ToolUseBlock(id="t1", name="Read", input={"file_path": "a.py"})))
    assert b.items["t1"]["status"] == "running"
    ops = b.feed(UserMessage(content=[ToolResultBlock(tool_use_id="t1", content="line1\nline2", is_error=False)]))
    assert ops[0]["item"] is b.items["t1"]
    assert b.items["t1"]["status"] == "done" and b.items["t1"]["result"] == "line1\nline2"


def test_failed_tool_is_marked_error():
    b = TranscriptBuilder()
    b.feed(assistant(ToolUseBlock(id="t1", name="Bash", input={"command": "x"})))
    b.feed(UserMessage(content=[ToolResultBlock(tool_use_id="t1", content="boom", is_error=True)]))
    assert b.items["t1"]["status"] == "error" and b.items["t1"]["is_error"] is True


def test_subagent_items_carry_their_parent():
    b = TranscriptBuilder()
    ops = b.feed(assistant(TextBlock(text="inner"), parent="t9"))
    assert ops[0]["item"]["parent"] == "t9"


def test_tool_results_for_unknown_tools_and_plain_user_messages_are_ignored():
    b = TranscriptBuilder()
    assert b.feed(UserMessage(content=[ToolResultBlock(tool_use_id="nope", content="x")])) == []
    assert b.feed(UserMessage(content="just text")) == []


def test_result_item_reports_cost_time_and_errors():
    b = TranscriptBuilder()
    ok = b.feed(result())[0]["item"]
    assert ok["kind"] == "result" and ok["ok"] is True and ok["ms"] == 1200 and ok["cost"] == 0.01 and ok["error"] is None
    bad = b.feed(result(is_error=True, text="rate limited"))[0]["item"]
    assert bad["ok"] is False and bad["error"] == "rate limited"


def test_session_info_comes_from_the_init_message():
    ops = TranscriptBuilder().feed(SystemMessage(subtype="init", data={"session_id": "abc", "model": "sonnet"}))
    assert ops == [{"op": "session", "session_id": "abc", "model": "sonnet"}]
    assert TranscriptBuilder().feed(SystemMessage(subtype="other", data={})) == []


def test_finish_turn_stops_running_tools_and_closes_live_text():
    b = TranscriptBuilder()
    b.feed(stream({"type": "content_block_start", "index": 0, "content_block": {"type": "text"}}))
    b.feed(assistant(ToolUseBlock(id="t1", name="Bash", input={})))
    ops = b.finish_turn()
    assert b.items["t1"]["status"] == "stopped"
    assert not any(i.get("live") for i in b.items.values())
    assert len(ops) == 2


def test_user_item_keeps_text_and_images():
    item = TranscriptBuilder().user("hi", [{"media_type": "image/png", "data": "AAA"}])[0]["item"]
    assert item["kind"] == "user" and item["text"] == "hi" and item["images"][0]["media_type"] == "image/png"


def test_result_text_joins_blocks_and_cuts_huge_output():
    assert result_text([{"type": "text", "text": "a"}, {"type": "image"}]) == "a\n[image]"
    assert result_text(None) == ""
    big = result_text("x" * (MAX_RESULT_CHARS + 50))
    assert big.startswith("x" * MAX_RESULT_CHARS) and "50 more characters" in big
