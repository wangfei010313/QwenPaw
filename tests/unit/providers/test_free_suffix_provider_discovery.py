# -*- coding: utf-8 -*-
"""Tests for public model discovery on free gateway providers."""

from types import SimpleNamespace

import pytest

from qwenpaw.providers.openai_provider import (
    KiloProvider,
    OpenCodeProvider,
)
from qwenpaw.providers.provider_manager import (
    PROVIDER_KILO,
    PROVIDER_OPENCODE,
    ProviderManager,
)


@pytest.mark.parametrize(
    ("provider_class", "free_suffix"),
    (
        (OpenCodeProvider, "-free"),
        (KiloProvider, ":free"),
    ),
)
async def test_free_gateway_discovery_normalizes_models(
    monkeypatch,
    provider_class,
    free_suffix: str,
) -> None:
    """Discovery should remove invalid IDs and mark free models."""
    provider = provider_class(
        id="gateway",
        name="Gateway",
        base_url="https://gateway.example/v1",
        require_api_key=False,
    )
    rows = [
        SimpleNamespace(id=f"vendor/free{free_suffix}"),
        SimpleNamespace(id=f"vendor/free{free_suffix}"),
        SimpleNamespace(id="vendor/paid"),
        SimpleNamespace(id="   "),
    ]

    class FakeModels:
        """Return a deterministic OpenAI-compatible model catalog."""

        async def list(self, timeout=None):
            _ = timeout
            return SimpleNamespace(data=rows)

    fake_client = SimpleNamespace(models=FakeModels())
    monkeypatch.setattr(
        provider,
        "_client",
        lambda timeout=5: fake_client,
    )

    models = await provider.fetch_models(timeout=3)

    assert [model.id for model in models] == [
        f"vendor/free{free_suffix}",
        "vendor/paid",
    ]
    assert [model.is_free for model in models] == [True, False]


def test_public_free_gateways_enable_model_discovery(
    isolated_secret_dir,
) -> None:
    """Built-in OpenCode and Kilo providers should expose discovery."""
    _ = isolated_secret_dir
    manager = ProviderManager()

    for provider_id in (PROVIDER_OPENCODE.id, PROVIDER_KILO.id):
        provider = manager.get_provider(provider_id)
        assert provider is not None
        assert provider.support_model_discovery is True
