# -*- coding: utf-8 -*-
"""Tests for auto context window detection feature."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from qwenpaw.providers.provider import Provider, ModelInfo
from qwenpaw.providers.openai_provider import OpenAIProvider
from qwenpaw.providers.ollama_provider import OllamaProvider
from qwenpaw.providers.anthropic_provider import AnthropicProvider
from qwenpaw.providers.gemini_provider import GeminiProvider
from qwenpaw.providers.openrouter_provider import OpenRouterProvider


class TestProviderBase(Provider):
    """Test provider implementation."""

    async def check_connection(self, timeout: float = 5):
        return True, ""

    async def fetch_models(self, timeout: float = 5):
        return []

    async def check_model_connection(self, model_id: str, timeout: float = 5):
        return True, ""

    def get_chat_model_instance(self, model_id: str):
        return MagicMock()


@pytest.mark.asyncio
async def test_provider_base_default_implementation():
    """Test that Provider base class returns None by default."""
    provider = TestProviderBase(
        id="test",
        name="Test Provider",
        base_url="http://test.com",
        api_key="test-key",
    )
    result = await provider.fetch_model_context_from_api("test-model")
    assert result is None


@pytest.mark.asyncio
async def test_openai_provider_fetch_context():
    """Test OpenAI provider fetches context window from /v1/models."""
    provider = OpenAIProvider(
        id="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key="test-key",
    )

    # Mock the client and response
    mock_model = MagicMock()
    mock_model.id = "gpt-4"
    mock_model.context_length = 128000

    mock_response = MagicMock()
    mock_response.data = [mock_model]

    with patch.object(provider, "_client") as mock_client:
        mock_client_instance = MagicMock()
        mock_client_instance.models.list = AsyncMock(return_value=mock_response)
        mock_client.return_value = mock_client_instance

        result = await provider.fetch_model_context_from_api("gpt-4")
        assert result == 128000


@pytest.mark.asyncio
async def test_openai_provider_fetch_context_not_found():
    """Test OpenAI provider returns None when model not found."""
    provider = OpenAIProvider(
        id="openai",
        name="OpenAI",
        base_url="https://api.openai.com/v1",
        api_key="test-key",
    )

    mock_response = MagicMock()
    mock_response.data = []

    with patch.object(provider, "_client") as mock_client:
        mock_client_instance = MagicMock()
        mock_client_instance.models.list = AsyncMock(return_value=mock_response)
        mock_client.return_value = mock_client_instance

        result = await provider.fetch_model_context_from_api("gpt-4")
        assert result is None


@pytest.mark.asyncio
async def test_ollama_provider_fetch_context():
    """Test Ollama provider fetches context window from /api/show."""
    provider = OllamaProvider(
        id="ollama",
        name="Ollama",
        base_url="http://localhost:11434",
        api_key="ollama",
    )

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "model_info": {"num_ctx": 4096}
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client_class.return_value = mock_client

        result = await provider.fetch_model_context_from_api("llama2")
        assert result == 4096


@pytest.mark.asyncio
async def test_anthropic_provider_fetch_context():
    """Test Anthropic provider fetches context window."""
    provider = AnthropicProvider(
        id="anthropic",
        name="Anthropic",
        base_url="https://api.anthropic.com",
        api_key="test-key",
    )

    mock_model = MagicMock()
    mock_model.context_window = 200000

    with patch.object(provider, "_client") as mock_client:
        mock_client_instance = MagicMock()
        mock_client_instance.models.retrieve = AsyncMock(return_value=mock_model)
        mock_client.return_value = mock_client_instance

        result = await provider.fetch_model_context_from_api("claude-3-opus")
        assert result == 200000


@pytest.mark.asyncio
async def test_gemini_provider_fetch_context():
    """Test Gemini provider fetches context window."""
    provider = GeminiProvider(
        id="gemini",
        name="Gemini",
        base_url="",
        api_key="test-key",
    )

    mock_model = MagicMock()
    mock_model.input_token_limit = 1000000

    with patch.object(provider, "_client") as mock_client:
        mock_client_instance = MagicMock()
        mock_client_instance.aio.models.get = AsyncMock(return_value=mock_model)
        mock_client.return_value = mock_client_instance

        result = await provider.fetch_model_context_from_api("gemini-pro")
        assert result == 1000000


@pytest.mark.asyncio
async def test_openrouter_provider_fetch_context():
    """Test OpenRouter provider fetches context window."""
    provider = OpenRouterProvider(
        id="openrouter",
        name="OpenRouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="test-key",
    )

    mock_model = MagicMock()
    mock_model.id = "openai/gpt-4"
    mock_model.context_length = 128000

    mock_response = MagicMock()
    mock_response.data = [mock_model]

    with patch.object(provider, "_client") as mock_client:
        mock_client_instance = MagicMock()
        mock_client_instance.models.list = AsyncMock(return_value=mock_response)
        mock_client.return_value = mock_client_instance

        result = await provider.fetch_model_context_from_api("openai/gpt-4")
        assert result == 128000


def test_context_window_resolution_with_auto_detected():
    """Test context window resolution with auto-detected value."""
    from qwenpaw.providers.context_windows import resolve_context_window

    # Test priority: explicit config > auto-detected > catalog > default
    result = resolve_context_window(
        "gpt-4",
        configured=None,
        configured_is_explicit=False,
        use_catalog=True,
        auto_detected=128000,
    )
    assert result == 128000

    # Explicit config should win
    result = resolve_context_window(
        "gpt-4",
        configured=64000,
        configured_is_explicit=True,
        use_catalog=True,
        auto_detected=128000,
    )
    assert result == 64000


def test_provider_get_context_size_with_auto_detected():
    """Test Provider.get_context_size uses auto-detected value."""
    provider = TestProviderBase(
        id="test",
        name="Test Provider",
        base_url="http://test.com",
        api_key="test-key",
        models=[
            ModelInfo(
                id="test-model",
                name="Test Model",
                max_input_length=131072,
                max_input_length_configured=False,
            )
        ],
    )

    # Add auto-detected value
    provider.models[0].max_input_length_auto_detected = 200000

    result = provider.get_context_size("test-model")
    assert result == 200000
