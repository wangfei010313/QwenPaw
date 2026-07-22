# -*- coding: utf-8 -*-
# pylint: disable=protected-access
from __future__ import annotations

from types import SimpleNamespace

import qwenpaw.providers.openai_provider as openai_provider_module
from qwenpaw.providers.dashscope_provider import DashScopeProvider
from qwenpaw.providers.openai_provider import OpenAIProvider


def _make_provider(is_custom: bool = False) -> OpenAIProvider:
    return OpenAIProvider(
        id="openai",
        name="OpenAI",
        base_url="https://mock-openai.local/v1",
        api_key="sk-test",
        is_custom=is_custom,
        chat_model="OpenAIChatModel",
    )


async def test_check_connection_success(monkeypatch) -> None:
    provider = _make_provider()
    calls: list[float | None] = []

    class FakeModels:
        async def list(self, timeout=None):
            calls.append(timeout)
            return SimpleNamespace(data=[])

    fake_client = SimpleNamespace(models=FakeModels())
    monkeypatch.setattr(provider, "_client", lambda timeout=5: fake_client)

    ok, msg = await provider.check_connection(timeout=2.5)

    assert ok is True
    assert msg == ""
    assert calls == [2.5]


async def test_check_connection_api_error_returns_false(monkeypatch) -> None:
    provider = _make_provider()

    class FakeModels:
        async def list(self, timeout=None):
            raise RuntimeError("boom")

    fake_client = SimpleNamespace(models=FakeModels())
    monkeypatch.setattr(provider, "_client", lambda timeout=5: fake_client)
    monkeypatch.setattr(openai_provider_module, "APIError", Exception)

    ok, msg = await provider.check_connection(timeout=1)

    assert ok is False
    assert msg.startswith(
        f"API error when connecting to `{provider.base_url}`",
    )


async def test_list_model_normalizes_and_deduplicates(monkeypatch) -> None:
    provider = _make_provider()
    rows = [
        SimpleNamespace(
            id="gpt-4o-mini",
            name="GPT-4o Mini",
            context_length=128_000,
            max_output_tokens=16_384,
        ),
        SimpleNamespace(id="gpt-4o-mini", name="dup"),
        SimpleNamespace(id="gpt-4.1", name=""),
        SimpleNamespace(id="   ", name="invalid"),
    ]

    class FakeModels:
        async def list(self, timeout=None):
            _ = timeout
            return SimpleNamespace(data=rows)

    fake_client = SimpleNamespace(models=FakeModels())
    monkeypatch.setattr(provider, "_client", lambda timeout=5: fake_client)

    models = await provider.fetch_models(timeout=3)

    assert [m.id for m in models] == ["gpt-4o-mini", "gpt-4.1"]
    assert [m.name for m in models] == ["GPT-4o Mini", "gpt-4.1"]
    assert models[0].max_input_length_auto_detected == 128_000
    assert models[0].max_tokens == 16_384
    assert not provider.models  # should not update provider state


async def test_list_model_api_error_returns_empty(monkeypatch) -> None:
    provider = _make_provider()

    class FakeModels:
        async def list(self, timeout=None):
            raise RuntimeError("failed")

    fake_client = SimpleNamespace(models=FakeModels())
    monkeypatch.setattr(provider, "_client", lambda timeout=5: fake_client)
    monkeypatch.setattr(openai_provider_module, "APIError", Exception)

    models = await provider.fetch_models(timeout=3)

    assert models == []


async def test_check_model_connection_success(monkeypatch) -> None:
    provider = _make_provider()
    captured: list[dict] = []

    class FakeStream:
        def __init__(self, chunks=None):
            self._chunks = iter(chunks or [])

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._chunks)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.append(kwargs)
            if "tools" not in kwargs:
                return FakeStream()
            function = SimpleNamespace(
                name="qwenpaw_connection_probe",
                arguments='{"value":"pong"}',
            )
            call = SimpleNamespace(function=function)
            delta = SimpleNamespace(tool_calls=[call])
            return FakeStream(
                [SimpleNamespace(choices=[SimpleNamespace(delta=delta)])],
            )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions()),
    )
    monkeypatch.setattr(provider, "_client", lambda timeout=5: fake_client)

    ok, msg = await provider.check_model_connection("gpt-4o-mini", timeout=4)

    assert ok is True
    assert msg == ""
    assert len(captured) == 2
    assert captured[0]["model"] == "gpt-4o-mini"
    assert captured[0]["timeout"] == 4
    assert captured[0]["max_tokens"] == 20
    assert captured[0]["stream"] is True
    assert "tools" not in captured[0]
    assert captured[1]["tools"][0]["type"] == "function"
    probe_name = "qwenpaw_connection_probe"
    assert captured[1]["tools"][0]["function"]["name"] == probe_name


async def test_check_gpt5_model_uses_max_completion_tokens(
    monkeypatch,
) -> None:
    provider = _make_provider()
    captured: list[dict] = []

    class FakeStream:
        def __init__(self, chunks=None):
            self._chunks = iter(chunks or [])

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._chunks)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.append(kwargs)
            if "tools" not in kwargs:
                return FakeStream()
            function = SimpleNamespace(
                name="qwenpaw_connection_probe",
                arguments='{"value":"pong"}',
            )
            call = SimpleNamespace(function=function)
            delta = SimpleNamespace(tool_calls=[call])
            return FakeStream(
                [SimpleNamespace(choices=[SimpleNamespace(delta=delta)])],
            )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions()),
    )
    monkeypatch.setattr(provider, "_client", lambda timeout=5: fake_client)

    ok, msg = await provider.check_model_connection("gpt-5.2", timeout=4)

    assert ok is True
    assert msg == ""
    assert captured[0]["max_completion_tokens"] == 20
    assert "max_tokens" not in captured[0]
    assert captured[1]["max_completion_tokens"] == 20


async def test_check_model_connection_rejects_missing_tool_support(
    monkeypatch,
) -> None:
    provider = _make_provider()
    call_count = 0

    class FakeStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class FakeCompletions:
        async def create(self, **kwargs):
            nonlocal call_count
            call_count += 1
            if "tools" in kwargs:
                raise RuntimeError("The tool call is not supported")
            return FakeStream()

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions()),
    )
    monkeypatch.setattr(provider, "_client", lambda timeout=5: fake_client)
    monkeypatch.setattr(openai_provider_module, "APIError", Exception)

    ok, msg = await provider.check_model_connection(
        "deepseek-r1-distill-qwen-14b",
        timeout=4,
    )

    assert ok is False
    assert call_count == 2
    assert msg.startswith("Tool calling check failed for model")
    assert msg.endswith("The tool call is not supported")


async def test_dashscope_tool_probe_retries_with_thinking_disabled(
    monkeypatch,
) -> None:
    provider = DashScopeProvider(
        id="dashscope",
        name="DashScope",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        api_key="sk-test",
    )
    captured: list[dict] = []

    class FakeStream:
        def __init__(self, chunks=None):
            self._chunks = iter(chunks or [])

        def __aiter__(self):
            return self

        async def __anext__(self):
            try:
                return next(self._chunks)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    class FakeCompletions:
        async def create(self, **kwargs):
            captured.append(kwargs)
            if "tools" not in kwargs:
                return FakeStream()
            if "extra_body" not in kwargs:
                raise RuntimeError(
                    "The tool_choice parameter does not support being set "
                    "to required or object in thinking mode",
                )
            function = SimpleNamespace(
                name="qwenpaw_connection_probe",
                arguments='{"value":"pong"}',
            )
            call = SimpleNamespace(function=function)
            delta = SimpleNamespace(tool_calls=[call])
            return FakeStream(
                [SimpleNamespace(choices=[SimpleNamespace(delta=delta)])],
            )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions()),
    )
    monkeypatch.setattr(provider, "_client", lambda timeout=5: fake_client)
    monkeypatch.setattr(openai_provider_module, "APIError", Exception)

    result = await provider.check_model_connection("qwen3.7-max")

    assert result.success is True
    assert result.supports_tool_calling is True
    assert len(captured) == 3
    assert captured[2]["extra_body"] == {
        "enable_thinking": False,
        "thinking": {"type": "disabled"},
    }


def test_token_limit_kwargs_handles_reasoning_model_ids() -> None:
    assert openai_provider_module._token_limit_kwargs(
        "openai/gpt-5-mini",
        200,
    ) == {"max_completion_tokens": 200}
    assert openai_provider_module._token_limit_kwargs(
        "o3",
        200,
    ) == {"max_completion_tokens": 200}
    assert openai_provider_module._token_limit_kwargs(
        "openai/o4-mini",
        200,
    ) == {"max_completion_tokens": 200}
    assert openai_provider_module._token_limit_kwargs(
        "openai/gpt-4o-mini",
        200,
    ) == {"max_tokens": 200}


def test_get_gpt5_model_maps_configured_max_tokens() -> None:
    provider = _make_provider()
    provider.generate_kwargs = {"max_tokens": 4096}

    model = provider.get_chat_model_instance("gpt-5.2")

    assert model.parameters.max_tokens is None
    assert model._extra_generate_kwargs == {
        "max_completion_tokens": 4096,
    }


def test_get_o_series_model_maps_configured_max_tokens() -> None:
    provider = _make_provider()
    provider.generate_kwargs = {"max_tokens": 4096}

    model = provider.get_chat_model_instance("o3")

    assert model.parameters.max_tokens is None
    assert model._extra_generate_kwargs == {
        "max_completion_tokens": 4096,
    }


def test_get_gpt5_model_preserves_explicit_max_completion_tokens() -> None:
    provider = _make_provider()
    provider.generate_kwargs = {
        "max_tokens": 4096,
        "max_completion_tokens": 2048,
    }

    model = provider.get_chat_model_instance("gpt-5-mini")

    assert model.parameters.max_tokens is None
    assert model._extra_generate_kwargs == {
        "max_completion_tokens": 2048,
    }


async def test_check_model_connection_api_error_returns_false(
    monkeypatch,
) -> None:
    provider = _make_provider()

    class FakeCompletions:
        async def create(self, **kwargs):
            _ = kwargs
            raise RuntimeError("failed")

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions()),
    )
    monkeypatch.setattr(provider, "_client", lambda timeout=5: fake_client)
    monkeypatch.setattr(openai_provider_module, "APIError", Exception)

    ok, msg = await provider.check_model_connection("gpt-4o-mini", timeout=4)

    assert ok is False
    assert msg.startswith(
        "API error when connecting to model 'gpt-4o-mini' (status=unknown): ",
    )
    assert msg.endswith("failed")


async def test_connection_error_redacts_credentials(monkeypatch) -> None:
    provider = _make_provider()

    class FakeModels:
        async def list(self, timeout=None):
            _ = timeout
            raise RuntimeError(
                "Authorization: Bearer sk-secret x-api-key=other-secret",
            )

    fake_client = SimpleNamespace(models=FakeModels())
    monkeypatch.setattr(provider, "_client", lambda timeout=5: fake_client)
    monkeypatch.setattr(openai_provider_module, "APIError", Exception)

    ok, message = await provider.check_connection()

    assert ok is False
    assert "sk-secret" not in message
    assert "other-secret" not in message
    assert "[redacted]" in message


async def test_update_config_updates_non_none_values_and_get_info() -> None:
    provider = _make_provider(is_custom=True)

    provider.update_config(
        {
            "name": "OpenAI Custom",
            "base_url": "https://new.example/v1",
            "api_key": "sk-new",
            "chat_model": "OpenAIChatModel",
            "api_key_prefix": "sk-",
            "generate_kwargs": {"temperature": 0.2, "top_p": 0.9},
        },
    )

    info = await provider.get_info(mock_secret=False)

    assert provider.name == "OpenAI Custom"
    assert provider.base_url == "https://new.example/v1"
    assert provider.api_key == "sk-new"
    assert provider.chat_model == "OpenAIChatModel"
    assert provider.api_key_prefix == "sk-"
    assert provider.generate_kwargs == {"temperature": 0.2, "top_p": 0.9}
    assert info.name == "OpenAI Custom"
    assert info.base_url == "https://new.example/v1"
    assert info.api_key == "sk-new"
    assert info.chat_model == "OpenAIChatModel"
    assert info.api_key_prefix == "sk-"
    assert info.generate_kwargs == {"temperature": 0.2, "top_p": 0.9}
    assert info.is_custom
    assert not info.support_connection_check


async def test_update_config_skips_none_values() -> None:  # noqa: E501
    provider = _make_provider()
    provider.api_key_prefix = "sk-"
    provider.generate_kwargs = {"temperature": 0.1}

    provider.update_config(
        {
            "name": None,
            "base_url": None,
            "api_key": None,
            "chat_model": None,
            "api_key_prefix": None,
            "generate_kwargs": None,
        },
    )

    info = await provider.get_info()

    assert provider.name == "OpenAI"
    assert provider.base_url == "https://mock-openai.local/v1"
    assert provider.api_key == "sk-test"
    assert provider.chat_model == "OpenAIChatModel"
    assert provider.api_key_prefix == "sk-"
    assert provider.generate_kwargs == {"temperature": 0.1}
    assert info.name == "OpenAI"
    assert info.base_url == "https://mock-openai.local/v1"
    assert info.api_key == "sk-******"
    assert info.chat_model == "OpenAIChatModel"
    assert info.api_key_prefix == "sk-"
    assert info.generate_kwargs == {"temperature": 0.1}


async def test_update_config_does_not_update_chat_model() -> None:
    provider = _make_provider()

    provider.update_config(
        {
            "chat_model": "AnotherChatModel",
            "name": "OpenAI Updated",
        },
    )

    info = await provider.get_info(mock_secret=False)

    assert provider.name == "OpenAI Updated"
    assert provider.chat_model == "OpenAIChatModel"
    assert info.name == "OpenAI Updated"
    assert info.chat_model == "OpenAIChatModel"


async def test_update_config_updates_chat_model_for_custom_provider() -> None:
    provider = _make_provider()
    provider.is_custom = True

    provider.update_config(
        {
            "chat_model": "AnotherChatModel",
            "name": "Custom OpenAI",
        },
    )

    info = await provider.get_info(mock_secret=False)

    assert provider.name == "Custom OpenAI"
    assert provider.chat_model == "AnotherChatModel"
    assert info.name == "Custom OpenAI"
    assert info.chat_model == "AnotherChatModel"


async def test_update_config_does_not_update_base_url_when_frozen() -> None:
    provider = _make_provider()
    provider.freeze_url = True

    provider.update_config(
        {
            "base_url": "https://blocked.example/v1",
            "api_key": "sk-frozen",
        },
    )

    info = await provider.get_info(mock_secret=False)

    assert provider.base_url == "https://mock-openai.local/v1"
    assert provider.api_key == "sk-frozen"
    assert info.base_url == "https://mock-openai.local/v1"
    assert info.api_key == "sk-frozen"
