# -*- coding: utf-8 -*-
"""Route tests for provider model discovery."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from fastapi import BackgroundTasks

from qwenpaw.app.routers.providers import (
    ProviderConfigRequest,
    configure_provider,
    discover_models,
)
from qwenpaw.providers.provider import ModelInfo, ProviderInfo


async def test_configure_provider_schedules_model_discovery() -> None:
    provider = SimpleNamespace(
        support_model_discovery=True,
        api_key="sk-test",
        require_api_key=True,
    )
    manager = MagicMock()
    manager.update_provider.return_value = True
    manager.get_provider.return_value = provider
    manager.get_provider_info = AsyncMock(
        return_value=ProviderInfo(id="openai", name="OpenAI"),
    )
    manager.discover_provider_models = AsyncMock()
    tasks = BackgroundTasks()

    result = await configure_provider(
        background_tasks=tasks,
        manager=manager,
        provider_id="openai",
        body=ProviderConfigRequest(api_key="sk-test"),
    )

    assert result.id == "openai"
    assert len(tasks.tasks) == 1
    task = tasks.tasks[0]
    assert task.func == manager.discover_provider_models
    assert task.args == ("openai",)
    assert task.kwargs == {"save": True}


async def test_discover_route_returns_sync_status() -> None:
    manager = MagicMock()
    manager.get_provider.return_value = SimpleNamespace()
    manager.update_provider.return_value = True
    manager.discover_provider_models = AsyncMock(
        return_value=SimpleNamespace(
            success=False,
            models=[ModelInfo(id="cached", name="Cached")],
            added_count=0,
            last_synced_at="2026-07-17T00:00:00+00:00",
            used_static_fallback=True,
            error="upstream unavailable",
        ),
    )

    result = await discover_models(
        manager=manager,
        provider_id="openai",
        body=None,
        save=True,
    )

    assert result.success is False
    assert result.used_static_fallback is True
    assert result.last_synced_at == "2026-07-17T00:00:00+00:00"
    assert result.message == "upstream unavailable"
    assert [model.id for model in result.models] == ["cached"]


async def test_discover_preview_does_not_persist_credentials() -> None:
    provider = MagicMock()
    provider.model_copy.return_value = provider
    manager = MagicMock()
    manager.get_provider.return_value = provider
    manager.discover_provider_models = AsyncMock(
        return_value=SimpleNamespace(
            success=True,
            models=[],
            added_count=0,
            last_synced_at=None,
            used_static_fallback=False,
            error=None,
        ),
    )

    await discover_models(
        manager=manager,
        provider_id="openai",
        body=SimpleNamespace(api_key="preview-key", base_url=None),
        save=False,
    )

    manager.update_provider.assert_not_called()
    provider.model_copy.assert_called_once_with(
        update={"api_key": "preview-key"},
    )
    manager.discover_provider_models.assert_awaited_once_with(
        "openai",
        save=False,
        provider_override=provider,
    )
