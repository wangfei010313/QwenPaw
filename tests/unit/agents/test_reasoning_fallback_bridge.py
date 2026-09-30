# -*- coding: utf-8 -*-
# pylint: disable=protected-access
"""Model→event bridge tests for fallback transparency metadata.

The pinned agentscope release drops ``ChatResponse.metadata`` when it
converts model output into agent events, so ``QwenPawAgent`` collects the
fallback data from the responses its own ``_call_model`` frame receives
and re-attaches it onto the events it yields.  These tests cover that real
chain: a model that actually falls back during ``Agent._reasoning``,
events that leave ``QwenPawAgent._reasoning`` carrying the notice, and the
fresh-task-per-event pull the runtime heartbeat performs.
"""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from typing import Any, AsyncGenerator

from agentscope.agent import Agent
from agentscope.event import ModelCallStartEvent, TextBlockStartEvent
from agentscope.message import AssistantMsg, Msg
from agentscope.model import ChatModelBase
from agentscope.model._model_response import ChatResponse

from qwenpaw.agents.react_agent import QwenPawAgent
from qwenpaw.loop.gates import StopAction
from qwenpaw.providers.fallback_chat_model import FallbackChatModel


class _FakeModel(ChatModelBase):
    def __init__(self, name: str, behavior: Any) -> None:
        super().__init__(
            credential=None,
            model=name,
            parameters=ChatModelBase.Parameters(),
            stream=False,
            context_size=32_768,
        )
        self.behavior = behavior

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        if isinstance(self.behavior, Exception):
            raise self.behavior
        return self.behavior()


class _HttpError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


def _response(text: str) -> ChatResponse:
    return ChatResponse(
        content=[{"type": "text", "text": text}],
        is_last=True,
    )


async def _stream(
    *items: ChatResponse,
) -> AsyncGenerator[ChatResponse, None]:
    for item in items:
        yield item


def _bare_agent(model: ChatModelBase) -> QwenPawAgent:
    """Build a minimal agent without running heavy __init__."""
    agent = object.__new__(QwenPawAgent)
    agent.model = model
    agent._context_manager = None
    agent._tool_schema_index = {}

    async def _noop() -> None:
        return None

    async def _stop_result(_final_msg: Any) -> Any:
        return SimpleNamespace(
            action=StopAction.BYPASS,
            final_message=None,
            reason="",
        )

    agent._inject_pending_hints = _noop
    agent._model_rejects_media = lambda: False
    agent._run_stop_handlers = _stop_result
    return agent


def _stub_base_reasoning(monkeypatch) -> None:
    """Drive the real ``_call_model`` seam from the base loop.

    Mirrors the production order: the model-call event is yielded before
    the call, so the call itself runs in a later pull than the one that
    entered the reply generator.
    """

    async def fake_base_call(
        self,
        messages: Any,
        tools: Any,
        tool_choice: Any = None,
    ) -> Any:
        del messages, tools, tool_choice
        return await self.model()

    async def fake_base_reasoning(self, tool_choice=None):
        del tool_choice
        yield ModelCallStartEvent(reply_id="r1", model_name="primary")
        response = await self._call_model(messages=[], tools=[])
        if inspect.isasyncgen(response):
            async for _chunk in response:
                pass
        yield TextBlockStartEvent(reply_id="r1", block_id="b1")
        yield AssistantMsg("agent", content=[])

    monkeypatch.setattr(Agent, "_call_model", fake_base_call)
    monkeypatch.setattr(Agent, "_reasoning", fake_base_reasoning)
    monkeypatch.setattr(
        "qwenpaw.loop.gates.runner.check_pending_gates",
        lambda _agent: None,
    )


async def _collect(agent: QwenPawAgent, *, pumped: bool) -> list[Any]:
    """Collect the events leaving ``_reasoning``.

    ``pumped`` pulls every event from a fresh task, the way the runtime
    heartbeat drives the reply stream, so a notice that only survives in
    the reply generator's own context would be lost.
    """
    stream = agent._reasoning()
    if not pumped:
        return [evt async for evt in stream]
    events: list[Any] = []
    while True:
        try:
            events.append(await asyncio.ensure_future(stream.__anext__()))
        except StopAsyncIteration:
            return events


def _notices(outputs: list[Any]) -> tuple[list[dict], dict]:
    """Return the notices attached after the model call.

    The first event leaves the loop before the model is called, so it
    must stay clean; the event that follows the call carries the notice
    and the persisted assistant message repeats it.
    """
    messages = [evt for evt in outputs if isinstance(evt, Msg)]
    assert len(messages) == 1
    carried = [
        evt
        for evt in outputs
        if not isinstance(evt, Msg)
        and "qwenpaw_model_fallbacks" in (getattr(evt, "metadata", None) or {})
    ]
    assert len(carried) == 1
    assert "qwenpaw_model_fallbacks" not in (outputs[0].metadata or {})
    event_notices = carried[0].metadata["qwenpaw_model_fallbacks"]
    actual = carried[0].metadata["qwenpaw_actual_model"]
    assert messages[0].metadata["qwenpaw_model_fallbacks"] == event_notices
    return event_notices, actual


async def test_reasoning_events_carry_fallback_metadata(
    monkeypatch,
) -> None:
    """Fallback data survives the model→event conversion boundary."""
    primary = _FakeModel("primary", _HttpError(429))
    fallback = _FakeModel("fallback", lambda: _response("ok"))
    model = FallbackChatModel([primary, fallback])
    agent = _bare_agent(model)
    _stub_base_reasoning(monkeypatch)

    outputs = await _collect(agent, pumped=False)

    event_notices, actual = _notices(outputs)
    assert len(event_notices) == 1
    assert event_notices[0]["type"] == "model_fallback"
    assert event_notices[0]["to_model_id"] == "fallback"
    assert actual["model_id"] == "fallback"


async def test_reasoning_events_carry_streamed_fallback_metadata(
    monkeypatch,
) -> None:
    """A streamed fallback is noticed on the chunk that carries it."""
    primary = _FakeModel("primary", _HttpError(503))
    fallback = _FakeModel("fallback", lambda: _stream(_response("ok")))
    model = FallbackChatModel([primary, fallback])
    agent = _bare_agent(model)
    _stub_base_reasoning(monkeypatch)

    outputs = await _collect(agent, pumped=False)

    event_notices, actual = _notices(outputs)
    assert event_notices[0]["to_model_id"] == "fallback"
    assert actual["model_id"] == "fallback"


async def test_notice_survives_a_task_per_event_pull(
    monkeypatch,
) -> None:
    """The notice reaches events pulled from a fresh task.

    The runtime heartbeat (``runtime/heartbeat.py``) drives the reply
    stream with ``ensure_future(stream.__anext__())``, so the model call
    runs in a task that never entered the reply generator.  Nothing may
    depend on a context variable set there.
    """
    primary = _FakeModel("primary", _HttpError(503))
    fallback = _FakeModel("fallback", lambda: _stream(_response("ok")))
    model = FallbackChatModel([primary, fallback])
    agent = _bare_agent(model)
    _stub_base_reasoning(monkeypatch)

    outputs = await _collect(agent, pumped=True)

    event_notices, actual = _notices(outputs)
    assert event_notices[0]["type"] == "model_fallback"
    assert event_notices[0]["to_model_id"] == "fallback"
    assert actual["model_id"] == "fallback"


async def test_reasoning_events_stay_clean_without_fallback(
    monkeypatch,
) -> None:
    """No fallback → no metadata keys injected into events."""
    only = _FakeModel("only", lambda: _response("ok"))
    model = FallbackChatModel([only])
    agent = _bare_agent(model)
    _stub_base_reasoning(monkeypatch)

    outputs = await _collect(agent, pumped=True)

    for evt in outputs:
        metadata = getattr(evt, "metadata", None) or {}
        assert "qwenpaw_model_fallbacks" not in metadata
