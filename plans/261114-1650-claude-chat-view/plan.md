# Claude chat view (option B): a separate screen next to the terminal

Goal: an agent can be opened as a **chat** (messages, tool cards, diffs, permission cards, paste/drop images)
instead of a terminal. Two separate screens; the terminal pane is unchanged. Claude first; other agents later
through the same normalized events.

## Decisions
- Backend drives Claude with `claude-agent-sdk` (streaming, image blocks, `can_use_tool`, interrupt, resume).
  Spike on this machine: text/tool/result streaming and file creation work. Needs the `claude` CLI installed.
- Normalized transcript items (the contract any adapter must fill): `user`, `text`, `thinking`, `tool`
  (name, input, result, status), `permission` (pending/allowed/denied), `result` (duration, cost), `notice`.
  Events to the UI: `item` (upsert by id), `delta` (append text), `remove`, `status`.
- A chat is its own object (not a PTY pane): listed in the sidebar under its space, own `chat.*` RPC methods,
  events on the existing hub (`ctx.hub.emit("chat", ...)`), history in `state_dir/chats/<id>.jsonl`.
- Phase 1 is local only (remote machines later). Images are sent as base64 content blocks, not files.
- The pane composer (option A) is removed: no shared input in the terminal.

## Phases
1. Backend: `herd/chat/` (events mapping, session, manager), `chat.*` RPC, snapshot field `chats`, tests.
2. Frontend core: chat store + event routing, sidebar rows, `chat` view, new-agent option "Chat".
3. Transcript UI: markdown-lite, tool cards (Read/Edit diff/Bash/generic), thinking, permission card, result line.
4. Composer: Enter sends, Stop button, images (paste/drop/pick), permission mode, model.
5. Polish: history reload, rename/close, errors, phone layout; docs.

## Not in phase 1
Remote machines, slash commands and `@file` picker, Codex/Gemini adapters, editing sent messages.

## Risks
- SDK/CLI event shapes change between versions: pin `claude-agent-sdk`, keep the mapping in one file with tests.
- User settings may auto-allow tools (permission cards then rarely appear). Verified by the spike.
- PyInstaller must bundle the SDK (hidden imports) and find the user's `claude` executable.

## Open questions
- Should the chat also be resumable in the terminal (`claude --resume`)? Possible later via `session_id`.
