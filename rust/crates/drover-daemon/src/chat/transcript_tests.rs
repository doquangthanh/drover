//! Same cases as `tests/test_chat_transcript_builder.py`, on the raw CLI messages.

use super::*;

fn stream(event: Value) -> Value {
    json!({"type": "stream_event", "uuid": "u", "session_id": "s", "event": event})
}

fn assistant(blocks: Value, parent: Option<&str>) -> Value {
    json!({"type": "assistant", "message": {"content": blocks}, "parent_tool_use_id": parent})
}

fn tool_result(id: &str, content: Value, is_error: bool) -> Value {
    json!({"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": id, "content": content, "is_error": is_error}]}})
}

fn result(is_error: bool, text: Option<&str>) -> Value {
    json!({"type": "result", "subtype": "success", "duration_ms": 1200, "is_error": is_error, "num_turns": 2,
           "session_id": "s", "total_cost_usd": 0.01, "result": text})
}

#[test]
fn streamed_text_grows_then_is_finalised_in_place() {
    let mut b = Transcript::default();
    let start = b.feed(&stream(json!({"type": "content_block_start", "index": 0, "content_block": {"type": "text"}})));
    let id = start[0]["item"]["id"].as_str().unwrap().to_string();
    assert_eq!(start[0]["item"]["live"], true);
    for t in ["Hel", "lo"] {
        let ops = b.feed(&stream(json!({"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": t}})));
        assert_eq!(ops, vec![json!({"op": "delta", "id": id, "text": t})]);
    }
    let fin = b.feed(&assistant(json!([{"type": "text", "text": "Hello"}]), None));
    assert_eq!(fin[0]["item"]["id"], json!(id));
    assert_eq!(fin[0]["item"]["text"], "Hello");
    assert_eq!(fin[0]["item"]["live"], false);
    assert_eq!(b.items.len(), 1);
}

#[test]
fn thinking_and_text_do_not_mix_up_when_both_stream() {
    let mut b = Transcript::default();
    b.feed(&stream(json!({"type": "content_block_start", "index": 0, "content_block": {"type": "thinking"}})));
    b.feed(&stream(json!({"type": "content_block_start", "index": 1, "content_block": {"type": "text"}})));
    b.feed(&stream(json!({"type": "content_block_delta", "index": 1, "delta": {"text": "answer"}})));
    b.feed(&stream(json!({"type": "content_block_delta", "index": 0, "delta": {"thinking": "hmm"}})));
    b.feed(&assistant(json!([{"type": "thinking", "thinking": "hmm", "signature": "x"}]), None));
    b.feed(&assistant(json!([{"type": "text", "text": "answer"}]), None));
    let kinds: Vec<(String, String)> = b.items.values()
        .map(|i| (i["kind"].as_str().unwrap().into(), i["text"].as_str().unwrap().into())).collect();
    assert_eq!(kinds, vec![("thinking".into(), "hmm".into()), ("text".into(), "answer".into())]);
    assert!(b.items.values().all(|i| i["live"] == false));
}

#[test]
fn message_without_streaming_still_produces_items() {
    let ops = Transcript::default().feed(&assistant(json!([{"type": "text", "text": "done"}]), None));
    assert_eq!(ops[0]["item"]["kind"], "text");
    assert_eq!(ops[0]["item"]["live"], false);
}

#[test]
fn tool_call_then_result_updates_the_same_item_and_errors_are_marked() {
    let mut b = Transcript::default();
    b.feed(&assistant(json!([{"type": "tool_use", "id": "t1", "name": "Read", "input": {"file_path": "a.py"}}]), None));
    assert_eq!(b.items["t1"]["status"], "running");
    let ops = b.feed(&tool_result("t1", json!("line1\nline2"), false));
    assert_eq!(ops[0]["item"], b.items["t1"]);
    assert_eq!(b.items["t1"]["status"], "done");
    assert_eq!(b.items["t1"]["result"], "line1\nline2");
    b.feed(&assistant(json!([{"type": "tool_use", "id": "t2", "name": "Bash", "input": {}}]), None));
    b.feed(&tool_result("t2", json!("boom"), true));
    assert_eq!(b.items["t2"]["status"], "error");
    assert_eq!(b.items["t2"]["is_error"], true);
}

#[test]
fn subagent_items_carry_their_parent() {
    let ops = Transcript::default().feed(&assistant(json!([{"type": "text", "text": "inner"}]), Some("t9")));
    assert_eq!(ops[0]["item"]["parent"], "t9");
}

#[test]
fn unknown_tool_results_and_plain_user_messages_are_ignored() {
    let mut b = Transcript::default();
    assert!(b.feed(&tool_result("nope", json!("x"), false)).is_empty());
    assert!(b.feed(&json!({"type": "user", "message": {"content": "just text"}})).is_empty());
}

#[test]
fn result_item_reports_cost_time_and_errors() {
    let mut b = Transcript::default();
    let ok = b.feed(&result(false, None))[0]["item"].clone();
    assert_eq!((ok["kind"].as_str(), ok["ok"].as_bool(), ok["ms"].as_i64(), ok["cost"].as_f64()), (Some("result"), Some(true), Some(1200), Some(0.01)));
    assert!(ok["error"].is_null());
    let bad = b.feed(&result(true, Some("rate limited")))[0]["item"].clone();
    assert_eq!(bad["ok"], false);
    assert_eq!(bad["error"], "rate limited");
}

#[test]
fn session_info_comes_from_the_init_message() {
    let ops = Transcript::default().feed(&json!({"type": "system", "subtype": "init", "session_id": "abc", "model": "sonnet"}));
    assert_eq!(ops, vec![json!({"op": "session", "session_id": "abc", "model": "sonnet"})]);
    assert!(Transcript::default().feed(&json!({"type": "system", "subtype": "other"})).is_empty());
}

#[test]
fn finish_turn_stops_running_tools_and_closes_live_text() {
    let mut b = Transcript::default();
    b.feed(&stream(json!({"type": "content_block_start", "index": 0, "content_block": {"type": "text"}})));
    b.feed(&assistant(json!([{"type": "tool_use", "id": "t1", "name": "Bash", "input": {}}]), None));
    let ops = b.finish_turn();
    assert_eq!(b.items["t1"]["status"], "stopped");
    assert!(b.items.values().all(|i| i["live"] != true));
    assert_eq!(ops.len(), 2);
}

#[test]
fn user_item_keeps_text_and_images() {
    let ops = Transcript::default().user("hi", &json!([{"media_type": "image/png", "data": "AAA"}]));
    assert_eq!(ops[0]["item"]["kind"], "user");
    assert_eq!(ops[0]["item"]["images"][0]["media_type"], "image/png");
}

#[test]
fn result_text_joins_blocks_and_cuts_huge_output() {
    assert_eq!(result_text(&json!([{"type": "text", "text": "a"}, {"type": "image"}])), "a\n[image]");
    assert_eq!(result_text(&Value::Null), "");
    let big = result_text(&json!("x".repeat(MAX_RESULT_CHARS + 50)));
    assert!(big.starts_with(&"x".repeat(MAX_RESULT_CHARS)) && big.contains("50 more characters"));
}
