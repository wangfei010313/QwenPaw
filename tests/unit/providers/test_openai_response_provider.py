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


async def test_check_model_compatibility_uses_responses_api(
    monkeypatch,
) -> None:
    provider = _make_provider()
    captured: list[dict] = []

    class FakeResponses:
        async def create(self, **kwargs):
            captured.append(kwargs)
            if "tools" not in kwargs:
                return SimpleNamespace(output=[])
            call = SimpleNamespace(
                type="function_call",
                name="qwenpaw_connection_probe",
                arguments='{"value":"pong"}',
            )
            return SimpleNamespace(output=[call])

    fake_client = SimpleNamespace(responses=FakeResponses())
    monkeypatch.setattr(provider, "_client", lambda timeout=5: fake_client)

    result = await provider.check_model_compatibility("gpt-5", timeout=4)

    assert result.success is True
    assert result.supports_tool_calling is True
    assert len(captured) == 2
    assert captured[1]["tool_choice"]["name"] == ("qwenpaw_connection_probe")


async def test_responses_api_ignored_tool_is_incompatible(monkeypatch) -> None:
    provider = _make_provider()

    class FakeResponses:
        async def create(self, **kwargs):
            _ = kwargs
            return SimpleNamespace(output=[])

    fake_client = SimpleNamespace(responses=FakeResponses())
    monkeypatch.setattr(provider, "_client", lambda timeout=5: fake_client)

    result = await provider.check_model_compatibility("gpt-5", timeout=4)

    assert result.success is False
    assert result.error_kind == "incompatible_api"
    assert result.supports_tool_calling is False
