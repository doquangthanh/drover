"""Chat sessions and manager with a fake Claude client: turns, images, permissions, interrupts, errors, persistence."""

from __future__ import annotations

import asyncio
from typing import ClassVar

import pytest
from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from herd.chat.chat_manager import ChatError, ChatManager
from herd.chat.chat_session import ChatBusy


def reply(text: str) -> AssistantMessage:
    return AssistantMessage(content=[TextBlock(text=text)], model="m")


def done() -> ResultMessage:
    return ResultMessage(subtype="success", duration_ms=5, duration_api_ms=4, is_error=False, num_turns=1,
                         session_id="sess-1", total_cost_usd=0.0)


class FakeClient:
    """Stands in for ClaudeSDKClient. `script(client)` is an async generator yielding the SDK messages of one turn."""

    instances: ClassVar[list[FakeClient]] = []

    def __init__(self, options, script) -> None:
        self.options, self.script = options, script
        self.prompts: list[dict] = []
        self.connected = self.disconnected = self.interrupted = False
        self.modes: list[str] = []
        self.models: list = []
        FakeClient.instances.append(self)

    async def connect(self) -> None:
        self.connected = True

    async def query(self, prompt) -> None:
        async for message in prompt:
            self.prompts.append(message)

    def receive_response(self):
        return self.script(self)

    async def interrupt(self) -> None:
        self.interrupted = True

    async def set_permission_mode(self, mode: str) -> None:
        self.modes.append(mode)

    async def disconnect(self) -> None:
        self.disconnected = True

    async def set_model(self, model) -> None:
        self.models.append(model)

    async def get_server_info(self) -> dict:
        return {"commands": [{"name": "compact", "description": "Summarize", "argumentHint": "[focus]"}, {"description": "nameless"}],
                "models": [{"value": "default", "displayName": "Default", "description": "Sonnet"}, {"value": "opus"}]}


@pytest.fixture
def events():
    return []


def make_manager(tmp_path, events, script):
    FakeClient.instances = []
    return ChatManager(tmp_path / "chats", lambda name, data: events.append((name, data)),
                       client_factory=lambda options: FakeClient(options, script))


async def settle(chat) -> None:
    await asyncio.wait_for(chat._task, 5)


async def say_hello(client):
    yield reply("Hello there")
    yield done()


async def test_a_turn_streams_items_and_returns_to_idle(tmp_path, events):
    manager = make_manager(tmp_path, events, say_hello)
    chat = manager.create(str(tmp_path))
    await chat.send("hi", [])
    assert chat.state == "working"
    await settle(chat)
    assert chat.state == "idle"
    kinds = [i["kind"] for i in chat.items()]
    assert kinds == ["user", "text", "result"]
    assert [d["op"] for n, d in events if n == "chat"] == ["item", "item", "item"]
    assert ("chats", manager.snapshot()) in events or any(n == "chats" for n, _ in events)


async def test_images_and_text_go_to_the_model_as_content_blocks(tmp_path, events):
    manager = make_manager(tmp_path, events, say_hello)
    chat = manager.create(str(tmp_path))
    await chat.send("what colour?", [{"media_type": "image/png", "data": "AAAA"}])
    await settle(chat)
    sent = FakeClient.instances[0].prompts[0]["message"]["content"]
    assert sent[0] == {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "AAAA"}}
    assert sent[1] == {"type": "text", "text": "what colour?"}


async def test_a_second_message_while_working_is_refused(tmp_path, events):
    release = asyncio.Event()

    async def slow(client):
        await release.wait()
        yield done()

    chat = make_manager(tmp_path, events, slow).create(str(tmp_path))
    await chat.send("one", [])
    with pytest.raises(ChatBusy):
        await chat.send("two", [])
    release.set()
    await settle(chat)
    await chat.send("three", [])  # idle again
    await settle(chat)


async def test_permission_request_waits_for_the_answer(tmp_path, events):
    async def needs_permission(client):
        decision = await client.options.can_use_tool("Bash", {"command": "ls"}, type("Ctx", (), {"title": "Run ls", "description": None, "suggestions": []})())
        yield reply(f"decision={decision.behavior}")
        yield done()

    chat = make_manager(tmp_path, events, needs_permission).create(str(tmp_path))
    await chat.send("go", [])
    for _ in range(100):
        await asyncio.sleep(0.01)
        if chat.state == "blocked":
            break
    assert chat.state == "blocked"
    pending = next(i for i in chat.items() if i["kind"] == "permission")
    assert pending["status"] == "pending" and pending["tool"] == "Bash"
    assert chat.answer(pending["id"], True) is True
    await settle(chat)
    assert next(i for i in chat.items() if i["kind"] == "permission")["status"] == "allowed"
    assert any(i["kind"] == "text" and i["text"] == "decision=allow" for i in chat.items())
    assert chat.answer("unknown", True) is False


async def test_denying_returns_a_deny_result(tmp_path, events):
    async def asks(client):
        decision = await client.options.can_use_tool("Write", {}, type("Ctx", (), {"title": None, "description": None, "suggestions": []})())
        yield reply(decision.behavior)
        yield done()

    chat = make_manager(tmp_path, events, asks).create(str(tmp_path))
    await chat.send("go", [])
    while chat.state != "blocked":
        await asyncio.sleep(0.01)
    chat.answer(next(i for i in chat.items() if i["kind"] == "permission")["id"], False)
    await settle(chat)
    assert any(i["kind"] == "text" and i["text"] == "deny" for i in chat.items())


async def test_interrupt_reaches_the_client_and_denies_open_questions(tmp_path, events):
    async def asks(client):
        decision = await client.options.can_use_tool("Bash", {}, type("Ctx", (), {"title": None, "description": None, "suggestions": []})())
        yield reply(decision.behavior)

    chat = make_manager(tmp_path, events, asks).create(str(tmp_path))
    await chat.send("go", [])
    while chat.state != "blocked":
        await asyncio.sleep(0.01)
    await chat.interrupt()
    await settle(chat)
    assert FakeClient.instances[0].interrupted is True
    assert chat.state == "idle"


async def test_a_crashing_client_becomes_an_error_notice_and_the_next_turn_reconnects(tmp_path, events):
    calls = {"n": 0}

    async def flaky(client):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("claude not found")
        yield reply("back")
        yield done()

    chat = make_manager(tmp_path, events, flaky).create(str(tmp_path))
    await chat.send("one", [])
    await settle(chat)
    assert any(i["kind"] == "notice" and "claude not found" in i["text"] for i in chat.items())
    assert FakeClient.instances[0].disconnected is True
    await chat.send("two", [])
    await settle(chat)
    assert len(FakeClient.instances) == 2 and any(i.get("text") == "back" for i in chat.items())


async def test_history_and_settings_survive_a_restart_and_resume_the_session(tmp_path, events):
    async def with_session(client):
        from claude_agent_sdk import SystemMessage

        yield SystemMessage(subtype="init", data={"session_id": "sess-1", "model": "sonnet"})
        yield reply("remembered")
        yield done()

    manager = make_manager(tmp_path, events, with_session)
    chat = manager.create(str(tmp_path), name="my chat", permission_mode="acceptEdits")
    await chat.send("hello", [])
    await settle(chat)
    await manager.shutdown()

    again = make_manager(tmp_path, [], with_session)
    restored = again.get(chat.id)
    assert restored.meta["name"] == "my chat" and restored.meta["session_id"] == "sess-1"
    assert [i["kind"] for i in restored.items()] == ["user", "text", "result"]
    await restored.send("more", [])
    await settle(restored)
    assert FakeClient.instances[-1].options.resume == "sess-1"
    assert FakeClient.instances[-1].options.permission_mode == "acceptEdits"


async def test_manager_validates_and_numbers_chats(tmp_path, events):
    manager = make_manager(tmp_path, events, say_hello)
    with pytest.raises(ChatError):
        manager.create(str(tmp_path / "missing"))
    with pytest.raises(ChatError):
        manager.create(str(tmp_path), permission_mode="yolo")
    assert [manager.create(str(tmp_path)).id, manager.create(str(tmp_path)).id] == ["c1", "c2"]
    with pytest.raises(ChatError):
        manager.get("c9")


async def test_remove_deletes_files_and_set_mode_reaches_a_live_client(tmp_path, events):
    manager = make_manager(tmp_path, events, say_hello)
    chat = manager.create(str(tmp_path))
    await chat.send("hi", [])
    await settle(chat)
    await chat.set_permission_mode("plan")
    assert FakeClient.instances[0].modes == ["plan"] and chat.meta["permission_mode"] == "plan"
    await manager.remove(chat.id)
    assert FakeClient.instances[0].disconnected is True
    assert not list((tmp_path / "chats").glob("c1.*"))
    assert manager.snapshot() == []


async def test_options_list_commands_and_models_once(tmp_path, events):
    chat = make_manager(tmp_path, events, say_hello).create(str(tmp_path))
    info = await chat.options()
    assert info["commands"] == [{"name": "compact", "description": "Summarize", "hint": "[focus]"}]
    assert info["models"] == [{"value": "default", "label": "Default", "description": "Sonnet"}, {"value": "opus", "label": "opus", "description": ""}]
    assert await chat.options() is info and len(FakeClient.instances) == 1  # cached, one CLI only
    await chat.send("hi", [])  # the same connection serves the next turn
    await settle(chat)
    assert len(FakeClient.instances) == 1


async def test_set_model_is_remembered_and_reaches_a_live_client(tmp_path, events):
    chat = make_manager(tmp_path, events, say_hello).create(str(tmp_path))
    await chat.set_model("opus")  # no client yet: only remembered, used when the CLI starts
    assert chat.meta["model"] == "opus" and not FakeClient.instances
    await chat.send("hi", [])
    await settle(chat)
    assert FakeClient.instances[0].options.model == "opus"
    await chat.set_model("default")
    assert FakeClient.instances[0].models == [None] and chat.meta["model"] is None
