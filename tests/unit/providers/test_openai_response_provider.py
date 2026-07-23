# -*- coding: utf-8 -*-
from __future__ import annotations

from types import SimpleNamespace

from qwenpaw.providers.openai_response_provider import OpenAIResponseProvider


def _make_provider() -> OpenAIResponseProvider:
    return OpenAIResponseProvider(
        id="openai-response",
        name="OpenAI Responses API",
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        chat_model="OpenAIResponseModel",
    )


async def test_check_model_connection_uses_basic_response(monkeypatch) -> None:
    provider = _make_provider()
    captured: list[dict] = []

    class FakeStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class FakeResponses:
        async def create(self, **kwargs):
            captured.append(kwargs)
            return FakeStream()

    fake_client = SimpleNamespace(responses=FakeResponses())
    monkeypatch.setattr(provider, "_client", lambda timeout=5: fake_client)

    ok, message = await provider.check_model_connection("gpt-5", timeout=4)

    assert ok is True
    assert message == ""
    assert captured == [
        {
            "model": "gpt-5",
            "input": "ping",
            "timeout": 4,
            "max_output_tokens": 20,
            "stream": True,
        },
    ]
    assert "tools" not in captured[0]
    assert "tool_choice" not in captured[0]


async def test_check_model_connection_rejects_empty_model() -> None:
    provider = _make_provider()

    ok, message = await provider.check_model_connection("   ")

    assert ok is False
    assert message == "Empty model ID"
