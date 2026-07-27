# -*- coding: utf-8 -*-
"""Tests for GitHub Models catalog discovery."""

from qwenpaw.providers.openai_provider import GitHubModelsProvider
from qwenpaw.providers.provider_manager import (
    PROVIDER_ALIYUN_CODINGPLAN,
    PROVIDER_ALIYUN_CODINGPLAN_INTL,
    PROVIDER_GITHUB_MODELS,
    ProviderManager,
)


async def test_github_catalog_filters_non_chat_and_maps_metadata(
    monkeypatch,
) -> None:
    """GitHub discovery should expose only text-output chat models."""
    provider = GitHubModelsProvider(
        id="github-models",
        name="GitHub Models",
        base_url="https://models.github.ai/inference",
    )
    payload = [
        {
            "id": "openai/gpt-test",
            "name": "GPT Test",
            "supported_input_modalities": ["text", "image"],
            "supported_output_modalities": ["text"],
            "limits": {
                "max_input_tokens": 128_000,
                "max_output_tokens": 16_384,
            },
        },
        {
            "id": "openai/text-embedding-test",
            "name": "Embedding Test",
            "supported_input_modalities": ["text"],
            "supported_output_modalities": ["embeddings"],
            "limits": {
                "max_input_tokens": 8_192,
                "max_output_tokens": None,
            },
        },
        {
            "id": "openai/gpt-test",
            "name": "Duplicate",
            "supported_output_modalities": ["text"],
        },
        {
            "id": "vendor/malformed-metadata",
            "name": "Malformed Metadata",
            "supported_input_modalities": None,
            "supported_output_modalities": ["text"],
            "limits": None,
        },
        {"id": "   ", "supported_output_modalities": ["text"]},
    ]

    class FakeResponse:
        """Return a deterministic public catalog response."""

        def raise_for_status(self) -> None:
            return None

        def json(self):
            return payload

    class FakeClient:
        """Async context manager used by the provider catalog request."""

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            _ = (exc_type, exc, traceback)
            return False

        async def get(self, url):
            assert url == "https://models.github.ai/catalog/models"
            return FakeResponse()

    monkeypatch.setattr(
        "qwenpaw.providers.openai_provider.httpx.AsyncClient",
        lambda **kwargs: FakeClient(),
    )

    models = await provider.fetch_models(timeout=3)

    assert [model.id for model in models] == [
        "openai/gpt-test",
        "vendor/malformed-metadata",
    ]
    assert models[0].name == "GPT Test"
    assert models[0].supports_multimodal is True
    assert models[0].supports_image is True
    assert models[0].supports_video is False
    assert models[0].max_input_length_auto_detected == 128_000
    assert models[0].max_tokens == 16_384
    assert models[0].probe_source == "api"


def test_public_catalog_providers_enable_discovery(
    isolated_secret_dir,
) -> None:
    """Providers with verified public catalogs should enable discovery."""
    _ = isolated_secret_dir
    manager = ProviderManager()
    provider_ids = (
        PROVIDER_ALIYUN_CODINGPLAN.id,
        PROVIDER_ALIYUN_CODINGPLAN_INTL.id,
        PROVIDER_GITHUB_MODELS.id,
    )

    for provider_id in provider_ids:
        provider = manager.get_provider(provider_id)
        assert provider is not None
        assert provider.support_model_discovery is True
