# Phase 04: Chat over the claude CLI

## Context Links
- `src/drover/chat/*`, `src/drover/rpc/methods_chat.py`, `tests/test_chat_*.py`, `tests/test_daemon_rpc_chat.py`

## Overview
- Priority: P2. Status: done (2026-11-18; chat view in the real UI not clicked through yet). Effort: 14h.
- `chat.*` methods without claude_agent_sdk: spawn `claude` and speak its stream-json protocol directly.

## Key Insights
- claude_agent_sdk is a wrapper around `claude --input-format stream-json --output-format stream-json` plus a stdio
  control protocol (interrupt, set model/mode, permission requests). Rust can do the same with no Python.
- Chat history format in `~/.local/state/drover/chats/` must stay readable by both daemons.

## Requirements
- Methods: chat.create/list/history/send/interrupt/answer/set_mode/set_model/options/rename/remove/files.
- Stream parser -> transcript builder (same event shapes the frontend chat view expects).
- Permission prompts: control requests from CLI -> `chat.answer` from UI -> control response.
- `claude_locator`: find the binary the same way (PATH, known install dirs, Windows `.cmd`).
- File search for `@` mentions (`chat.files`).

## Architecture
```
chat.send ─> ChatSession ── stdin (stream-json user msg) ──> claude process
UI <─ ev chat ─ TranscriptBuilder <── stdout (stream-json events / control_request)
chat.answer ──────────────── stdin (control_response) ───────────┘
```

## Related Code Files
- Create: `rust/crates/drover-daemon/src/chat/{chat_manager.rs, chat_session.rs, stream_json.rs, control_protocol.rs,
  transcript_builder.rs, chat_store.rs, claude_locator.rs, file_search.rs}`, `methods/chat.rs`

## Implementation Steps
1. Capture real traffic: log what claude_agent_sdk writes/reads for a session with a permission prompt, interrupt and
   model change; save as fixtures.
2. Implement stream + control protocol against fixtures, then against the real CLI.
3. Port transcript builder with `test_chat_transcript_builder.py` cases as Rust tests.
4. Run `test_daemon_rpc_chat.py` against the binary.

## Todo List
- [x] protocol taken from the installed claude_agent_sdk 0.2.182 source (flags, initialize, can_use_tool,
  control_cancel_request, interrupt/set_model/set_permission_mode) instead of captured traffic;
  `src/chat/fake_claude.py` speaks it for tests
- [x] stream-json + control protocol (`chat/cli_process.rs`), session + permissions (`chat/session*.rs`)
- [x] transcript builder parity: all `test_chat_transcript_builder.py` cases ported (`chat/transcript_tests.rs`)
- [x] chat store compatible (same `<id>.json` + `<id>.jsonl`), file search, claude locator
- [x] `test_daemon_rpc_chat.py` green against the release `dr` (3/3); 17 Rust unit tests incl. a full turn on the fake CLI
- [x] real claude 2.1.327 through `/rpc`: options (130 commands, 5 models), Bash tool turn, Write permission asked and
  allowed (working -> blocked -> idle), interrupt while blocked denies and stops, session_id saved, no claude left
  after the daemon stops
- [ ] chat view clicked through in the window (send, stream, permission buttons, model picker)

## Success Criteria
- Chat view works end to end (send, stream, permission prompt, interrupt, model switch) with the Rust daemon.

## Risk Assessment
- Undocumented control protocol may change between claude versions: version-check at start, clear error in UI.

## Security Considerations
- Never pass user text through a shell; pass args as a vector. Keep permission default = ask.

## Next Steps
- Phase 05.
