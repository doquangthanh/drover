#!/usr/bin/env python3
"""Test stand-in for `claude --input-format stream-json`: answers initialize, then for each user message streams
"Hello", asks permission for Bash and echoes the answer it got, then ends the turn. Records its argv."""
import json, os, sys

def out(msg):
    sys.stdout.write(json.dumps(msg) + "\n"); sys.stdout.flush()

open(os.environ["FAKE_CLAUDE_ARGS"], "w").write(json.dumps(sys.argv[1:]))
for line in sys.stdin:
    msg = json.loads(line)
    if msg["type"] == "control_request":
        sub = msg["request"]["subtype"]
        resp = {"commands": [{"name": "help", "description": "d", "argumentHint": ""}], "models": [{"value": "opus", "displayName": "Opus"}]} if sub == "initialize" else {}
        out({"type": "control_response", "response": {"subtype": "success", "request_id": msg["request_id"], "response": resp}})
    elif msg["type"] == "user":
        out({"type": "system", "subtype": "init", "session_id": "sess-1", "model": "opus"})
        out({"type": "stream_event", "uuid": "u", "session_id": "sess-1", "event": {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}}})
        out({"type": "stream_event", "uuid": "u", "session_id": "sess-1", "event": {"type": "content_block_delta", "index": 0, "delta": {"text": "Hello"}}})
        out({"type": "assistant", "message": {"content": [{"type": "text", "text": "Hello"}]}, "parent_tool_use_id": None})
        out({"type": "control_request", "request_id": "perm1", "request": {"subtype": "can_use_tool", "tool_name": "Bash", "input": {"command": "ls"},
             "permission_suggestions": [{"type": "addRules", "rules": [{"toolName": "Bash"}], "behavior": "allow", "destination": "session"}]}})
        answer = json.loads(sys.stdin.readline())
        out({"type": "assistant", "message": {"content": [{"type": "text", "text": json.dumps(answer["response"]["response"])}]}, "parent_tool_use_id": None})
        out({"type": "result", "subtype": "success", "duration_ms": 5, "is_error": False, "num_turns": 1, "session_id": "sess-1", "total_cost_usd": 0.0})
