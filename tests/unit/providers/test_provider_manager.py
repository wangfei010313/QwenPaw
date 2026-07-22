# -*- coding: utf-8 -*-
# pylint: disable=redefined-outer-name,unused-argument,protected-access
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

import qwenpaw.providers.provider_manager as provider_manager_module
from qwenpaw.config.config import ModelSlotConfig
from qwenpaw.exceptions import ModelNotFoundException, ProviderError
from qwenpaw.local_models.llamacpp import LlamaCppServerSetupResult
from qwenpaw.providers.anthropic_provider import AnthropicProvider
from qwenpaw.providers.capping_formatter import (
    _CappingAnthropicFormatter,
    _CappingGeminiFormatter,
    _CappingOpenAIFormatter,
)
from qwenpaw.providers.context_windows import DEFAULT_CONTEXT_WINDOW
from qwenpaw.providers.openai_provider import (
    GitHubModelsProvider,
    OpenAIProvider,
)
from qwenpaw.providers.openrouter_provider import OpenRouterProvider
from qwenpaw.providers.provider import ModelInfo, ProviderInfo
from qwenpaw.providers.provider_manager import ProviderManager

LEGACY_PROVIDER = {
    "providers": {
        "modelscope": {
            "base_url": "https://api-inference.modelscope.cn/v1",
            "api_key": "",
            "extra_models": [],
            "chat_model": "",
        },
        "dashscope": {
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "sk-test-legacy-secret",
            "extra_models": [{"id": "qwen-plus", "name": "Qwen Plus"}],
            "chat_model": "",
        },
        "aliyun-codingplan": {
            "base_url": "https://coding.dashscope.aliyuncs.com/v1",
            "api_key": "",
            "extra_models": [],
            "chat_model": "",
        },
        "openai": {
            "base_url": "https://api.openai.com/v1",
            "api_key": "",
            "extra_models": [],
            "chat_model": "",
        },
        "azure-openai": {
            "base_url": "",
            "api_key": "",
            "extra_models": [],
            "chat_model": "",
        },
        "anthropic": {
            "base_url": "https://api.anthropic.com/v1",
            "api_key": "",
            "extra_models": [],
            "chat_model": "",
        },
        "ollama": {
            "base_url": "http://myhost:11434/v1",
            "api_key": "",
            "extra_models": [],
            "chat_model": "",
        },
    },
    "custom_providers": {
        "mydash": {
            "id": "mydash",
            "name": "MyDash",
            "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",  # noqa: E501
            "api_key_prefix": "sk-",
            "models": [{"id": "qwen3-max", "name": "qwen3-max"}],
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key": "sk-test-legacy-custom-secret",
            "chat_model": "OpenAIChatModel",
        },
    },
    "active_llm": {"provider_id": "dashscope", "model": "qwen3-max"},
}


@pytest.fixture
def isolated_secret_dir(monkeypatch, tmp_path):
    secret_dir = tmp_path / ".qwenpaw.secret"
    monkeypatch.setattr(provider_manager_module, "SECRET_DIR", secret_dir)
    return secret_dir


def test_builtin_zhipu_providers_registered(isolated_secret_dir) -> None:
    manager = ProviderManager()

    expected_configs = {
        "zhipu-cn": {
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "support_connection_check": True,
        },
        "zhipu-cn-codingplan": {
            "base_url": "https://open.bigmodel.cn/api/coding/paas/v4",
            "support_connection_check": False,
        },
        "zhipu-intl": {
            "base_url": "https://api.z.ai/api/paas/v4",
            "support_connection_check": True,
        },
        "zhipu-intl-codingplan": {
            "base_url": "https://api.z.ai/api/coding/paas/v4",
            "support_connection_check": False,
        },
    }

    for provider_id, expected in expected_configs.items():
        provider = manager.get_provider(provider_id)

        assert provider is not None
        assert isinstance(provider, OpenAIProvider)
        assert provider.base_url == expected["base_url"]
        assert provider.freeze_url is True
        assert (
            provider.support_connection_check
            == expected["support_connection_check"]
        )
        model_ids = [m.id for m in provider.models]
        assert len(model_ids) > 0
        assert len(model_ids) == len(set(model_ids))


async def test_add_custom_provider_and_reload_from_storage(
    isolated_secret_dir,
) -> None:
    manager = ProviderManager()
    custom = OpenAIProvider(
        id="custom-openai",
        name="Custom OpenAI",
        base_url="https://custom.example/v1",
        api_key="sk-custom",
        models=[ModelInfo(id="custom-model", name="Custom Model")],
    )

    created = await manager.add_custom_provider(custom)
    assert created.support_model_discovery is True
    builtin_conflict = await manager.add_custom_provider(
        OpenAIProvider(
            id="openai",
            name="Conflict OpenAI",
        ),
    )
    duplicate = await manager.add_custom_provider(custom)

    reloaded = ProviderManager()
    loaded = reloaded.get_provider("custom-openai")
    loaded_builtin_conflict = reloaded.get_provider("openai-custom")
    loaded_duplicate = reloaded.get_provider("custom-openai-new")

    assert created.id == "custom-openai"
    assert builtin_conflict.id == "openai-custom"
    assert duplicate.id == "custom-openai-new"
    assert loaded is not None
    assert isinstance(loaded, OpenAIProvider)
    assert loaded.is_custom is True
    assert loaded.base_url == "https://custom.example/v1"
    assert loaded.api_key == "sk-custom"
    assert [m.id for m in loaded.models] == ["custom-model"]
    assert loaded_builtin_conflict is not None
    assert isinstance(loaded_builtin_conflict, OpenAIProvider)
    assert loaded_duplicate is not None
    assert isinstance(loaded_duplicate, OpenAIProvider)


async def test_custom_provider_preserves_explicit_default_context_window(
    isolated_secret_dir,
) -> None:
    manager = ProviderManager()
    request_model = ModelInfo(
        id="claude-sonnet-4-5",
        name="Claude Sonnet 4.5",
        max_input_length=DEFAULT_CONTEXT_WINDOW,
    )
    assert "max_input_length" in request_model.model_fields_set
    assert request_model.max_input_length_configured is False

    await manager.add_custom_provider(
        ProviderInfo(
            id="custom-context-window",
            name="Custom Context Window",
            chat_model="OpenAIChatModel",
            extra_models=[request_model],
        ),
    )

    reloaded = ProviderManager().get_provider("custom-context-window")
    assert reloaded is not None
    model = reloaded.get_model_info("claude-sonnet-4-5")
    assert model is not None
    assert model.max_input_length_configured is True
    assert (
        reloaded.get_context_size("claude-sonnet-4-5")
        == DEFAULT_CONTEXT_WINDOW
    )


async def test_activate_provider_persists_active_model(
    isolated_secret_dir,
    monkeypatch,
) -> None:
    manager = ProviderManager()

    class FakeCompletions:
        async def create(self, **kwargs):
            return SimpleNamespace(id="ok", request=kwargs)

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions()),
    )

    monkeypatch.setattr(
        OpenAIProvider,
        "_client",
        lambda self, timeout=5: fake_client,
    )

    await manager.activate_model("openai", "gpt-5")

    assert manager.active_model is not None
    assert manager.active_model.provider_id == "openai"
    assert manager.active_model.model == "gpt-5"

    reloaded = ProviderManager()
    assert reloaded.active_model is not None
    assert reloaded.active_model.provider_id == "openai"
    assert reloaded.active_model.model == "gpt-5"


async def test_resume_local_model_restores_server_and_runtime_state(
    isolated_secret_dir,
) -> None:
    manager = ProviderManager()
    model_id = "AgentScope/QwenPaw-Flash-2B-Q4_K_M"
    manager.update_provider(
        "qwenpaw-local",
        {
            "base_url": "http://127.0.0.1:9000/v1",
            "extra_models": [
                {
                    "id": model_id,
                    "name": model_id,
                },
            ],
        },
    )
    manager.active_model = ModelSlotConfig(
        provider_id="qwenpaw-local",
        model=model_id,
    )
    manager.save_active_model(manager.active_model)

    class FakeLocalManager:
        def __init__(self) -> None:
            self.restored_model_id = None

        def check_llamacpp_installation(self) -> tuple[bool, str]:
            return True, ""

        def is_model_downloaded(self, requested_model_id: str) -> bool:
            return requested_model_id == model_id

        async def setup_server(
            self,
            requested_model_id: str,
        ) -> LlamaCppServerSetupResult:
            self.restored_model_id = requested_model_id
            return LlamaCppServerSetupResult(
                port=43111,
                model_info=ModelInfo(
                    id=requested_model_id,
                    name=requested_model_id,
                    supports_multimodal=True,
                    supports_image=True,
                    supports_video=True,
                    probe_source="documentation",
                ),
            )

    local_manager = FakeLocalManager()

    await manager._resume_local_model(local_manager)

    provider = manager.get_provider("qwenpaw-local")

    assert local_manager.restored_model_id == model_id
    assert provider is not None
    assert provider.base_url == "http://127.0.0.1:43111/v1"
    assert [model.id for model in provider.extra_models] == [model_id]
    assert provider.extra_models[0].supports_multimodal is True
    assert provider.extra_models[0].supports_image is True
    assert provider.extra_models[0].supports_video is True
    assert provider.extra_models[0].probe_source == "documentation"


async def test_remove_custom_provider_missing_file_is_safe(
    isolated_secret_dir,
) -> None:
    manager = ProviderManager()
    custom = OpenAIProvider(
        id="custom-to-remove",
        name="Custom To Remove",
        base_url="https://remove.example/v1",
        api_key="sk-remove",
    )
    await manager.add_custom_provider(custom)

    custom_path = manager.custom_path / "custom-to-remove.json"
    custom_path.unlink()

    manager.remove_custom_provider("custom-to-remove")

    assert manager.get_provider("custom-to-remove") is None


def test_load_provider_invalid_json_returns_none(isolated_secret_dir) -> None:
    manager = ProviderManager()
    bad_file = manager.custom_path / "bad-provider.json"
    bad_file.write_text("{invalid-json", encoding="utf-8")

    loaded = manager.load_provider("bad-provider", is_builtin=False)

    assert loaded is None


def test_migrate_legacy_file_and_persist_active_model(
    isolated_secret_dir,
) -> None:
    isolated_secret_dir.mkdir(parents=True, exist_ok=True)
    legacy_file = isolated_secret_dir / "providers.json"
    legacy_file.write_text(
        json.dumps(
            LEGACY_PROVIDER,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    manager = ProviderManager()

    assert legacy_file.exists() is False
    assert manager.active_model is not None
    assert manager.active_model.provider_id == "dashscope"
    assert manager.active_model.model == "qwen3-max"

    dashscope_provider = manager.get_provider("dashscope")
    assert dashscope_provider is not None
    assert dashscope_provider.api_key == "sk-test-legacy-secret"

    legacy_custom = manager.get_provider("mydash")
    assert legacy_custom is not None
    assert isinstance(legacy_custom, OpenAIProvider)
    assert len(legacy_custom.extra_models) == 1
    assert legacy_custom.extra_models[0].id == "qwen3-max"
    assert legacy_custom.api_key == "sk-test-legacy-custom-secret"

    legacy_ollama = manager.get_provider("ollama")
    assert legacy_ollama.base_url == "http://myhost:11434"

    active_model_file = isolated_secret_dir / "providers" / "active_model.json"
    assert active_model_file.exists()


async def test_add_custom_provider_conflict_resolution_loops_until_unique(
    isolated_secret_dir,
) -> None:
    manager = ProviderManager()
    conflict = OpenAIProvider(
        id="openai",
        name="Conflict OpenAI",
    )

    first = await manager.add_custom_provider(conflict)
    second = await manager.add_custom_provider(conflict)
    third = await manager.add_custom_provider(conflict)

    assert first.id == "openai-custom"
    assert second.id == "openai-custom-new"
    assert third.id == "openai-custom-new-new"

    assert manager.get_provider("openai-custom") is not None
    assert manager.get_provider("openai-custom-new") is not None
    assert manager.get_provider("openai-custom-new-new") is not None


def test_update_provider_for_builtin_persists_to_builtin_path(
    isolated_secret_dir,
) -> None:
    manager = ProviderManager()

    ok = manager.update_provider(
        "openai",
        {
            "base_url": "https://updated.example/v1",  # not taken effect
            "api_key": "sk-updated",
        },
    )

    assert ok is True
    persisted = manager.load_provider("openai", is_builtin=True)
    assert persisted is not None
    assert isinstance(persisted, OpenAIProvider)
    assert persisted.base_url == "https://api.openai.com/v1"
    assert persisted.api_key == "sk-updated"

    ok = manager.update_provider(
        "azure-openai",
        {
            "base_url": "https://azure-updated.example/v1",
            "api_key": "sk-azure-updated",
        },
    )
    assert ok is True
    persisted_azure = manager.load_provider("azure-openai", is_builtin=True)
    assert persisted_azure is not None
    assert isinstance(persisted_azure, OpenAIProvider)
    assert persisted_azure.base_url == "https://azure-updated.example/v1"
    assert persisted_azure.api_key == "sk-azure-updated"


@pytest.mark.parametrize(
    ("saved_length", "expected_configured"),
    [
        (64_000, True),
        (DEFAULT_CONTEXT_WINDOW, False),
    ],
)
def test_legacy_builtin_context_window_infers_non_default_as_configured(
    isolated_secret_dir,
    saved_length: int,
    expected_configured: bool,
) -> None:
    manager = ProviderManager()
    provider = manager.get_provider("openai")
    assert provider is not None
    data = provider.model_dump()
    for model in data["models"]:
        model.pop("max_input_length_configured", None)
        if model["id"] == "gpt-4o":
            model["max_input_length"] = saved_length

    builtin_path = isolated_secret_dir / "providers" / "builtin"
    (builtin_path / "openai.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    reloaded = ProviderManager().get_provider("openai")
    assert reloaded is not None
    model = reloaded.get_model_info("gpt-4o")
    assert model is not None
    assert model.max_input_length == saved_length
    assert model.max_input_length_configured is expected_configured


def test_builtin_capability_probe_results_survive_storage_reload(
    isolated_secret_dir,
) -> None:
    manager = ProviderManager()
    provider = manager.get_provider("openai")
    assert provider is not None
    data = provider.model_dump()
    for model in data["models"]:
        if model["id"] == "gpt-4o":
            model["supports_multimodal"] = False
            model["supports_image"] = False
            model["supports_video"] = False

    builtin_path = isolated_secret_dir / "providers" / "builtin"
    (builtin_path / "openai.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    reloaded = ProviderManager().get_provider("openai")
    assert reloaded is not None
    model = reloaded.get_model_info("gpt-4o")
    assert model is not None
    assert model.supports_multimodal is False
    assert model.supports_image is False
    assert model.supports_video is False


def test_update_provider_for_unknown_returns_false(
    isolated_secret_dir,
) -> None:
    manager = ProviderManager()

    ok = manager.update_provider("unknown-provider", {"api_key": "sk-x"})

    assert ok is False


async def test_discovery_keeps_user_models_and_persists_cache(
    isolated_secret_dir,
    monkeypatch,
) -> None:
    manager = ProviderManager()
    provider = manager.get_provider("openai")
    assert provider is not None
    provider.discovered_models = []
    provider.extra_models = [
        ModelInfo(id="user-only", name="User Only", source="user"),
    ]

    async def fetch_models(_self, timeout=5):
        assert timeout == 10
        return [
            ModelInfo(
                id="remote-new",
                name="Remote New",
                max_input_length_auto_detected=256_000,
            ),
        ]

    monkeypatch.setattr(OpenAIProvider, "fetch_models", fetch_models)

    result = await manager.discover_provider_models("openai")

    assert result.success is True
    assert result.added_count == 1
    assert result.last_synced_at
    assert [model.id for model in provider.extra_models] == ["user-only"]
    assert [model.id for model in provider.discovered_models] == [
        "remote-new",
    ]
    assert provider.discovered_models[0].source == "discovered"
    candidate = provider.get_discovered_model_info("remote-new")
    assert candidate is not None
    assert candidate.max_input_length_auto_detected == 256_000

    reloaded = ProviderManager().get_provider("openai")
    assert reloaded is not None
    assert reloaded.has_model("user-only")
    assert not reloaded.has_model("remote-new")
    assert reloaded.get_discovered_model_info("remote-new") is not None
    assert reloaded.models_last_synced_at == result.last_synced_at


async def test_failed_discovery_preserves_last_cache_and_user_models(
    isolated_secret_dir,
    monkeypatch,
) -> None:
    manager = ProviderManager()
    provider = manager.get_provider("openai")
    assert provider is not None
    provider.discovered_models = []
    provider.discovered_models = [
        ModelInfo(
            id="cached-remote",
            name="Cached Remote",
            source="discovered",
        ),
    ]
    provider.extra_models = [
        ModelInfo(id="user-only", name="User Only", source="user"),
    ]

    async def fetch_models(_self, timeout=5):
        raise TimeoutError("model discovery timed out")

    monkeypatch.setattr(OpenAIProvider, "fetch_models", fetch_models)

    result = await manager.discover_provider_models("openai")

    assert result.success is False
    assert result.used_static_fallback is True
    assert result.error == "model discovery timed out"
    assert provider.models_last_sync_error == result.error
    assert [model.id for model in provider.discovered_models] == [
        "cached-remote",
    ]
    assert [model.id for model in provider.extra_models] == ["user-only"]
    assert {model.id for model in result.models} >= {"cached-remote"}
    assert "user-only" not in {model.id for model in result.models}


async def test_discovery_deduplicates_and_preserves_builtin_metadata(
    isolated_secret_dir,
    monkeypatch,
) -> None:
    manager = ProviderManager()
    provider = manager.get_provider("openai")
    assert provider is not None
    provider.discovered_models = []
    builtin = provider.models[0]
    builtin.supports_image = True

    async def fetch_models(_self, timeout=5):
        return [
            ModelInfo(id=builtin.id, name="Remote Name"),
            ModelInfo(id=builtin.id, name="Duplicate"),
        ]

    monkeypatch.setattr(OpenAIProvider, "fetch_models", fetch_models)

    result = await manager.discover_provider_models("openai", save=False)

    assert result.success is True
    assert len(result.models) == 1
    assert result.models[0].name == "Remote Name"
    assert result.models[0].supports_image is True
    assert provider.discovered_models == []


async def test_discovery_preserves_explicit_context_override(
    isolated_secret_dir,
    monkeypatch,
) -> None:
    manager = ProviderManager()
    provider = manager.get_provider("openrouter")
    assert provider is not None
    provider.discovered_models = [
        ModelInfo(
            id="vendor/model",
            name="Configured Model",
            source="discovered",
            max_input_length=64_000,
            max_input_length_configured=True,
        ),
    ]

    async def fetch_models(_self, timeout=5):
        return [
            ModelInfo(
                id="vendor/model",
                name="Remote Model",
                max_input_length=1_000_000,
                max_input_length_auto_detected=1_000_000,
            ),
        ]

    monkeypatch.setattr(OpenRouterProvider, "fetch_models", fetch_models)

    result = await manager.discover_provider_models("openrouter")

    assert result.success is True
    model = provider.get_discovered_model_info("vendor/model")
    assert model is not None
    assert model.max_input_length == 64_000
    assert model.max_input_length_configured is True
    assert model.max_input_length_auto_detected == 1_000_000
    assert provider.get_context_size("vendor/model") == DEFAULT_CONTEXT_WINDOW


async def test_discovery_applies_metadata_to_configured_model(
    isolated_secret_dir,
    monkeypatch,
) -> None:
    manager = ProviderManager()
    provider = manager.get_provider("openai")
    assert provider is not None
    configured = provider.models[0]
    configured.max_tokens = 1024
    configured.config_overrides = ["max_tokens"]

    async def fetch_models(_self, timeout=5):
        _ = timeout
        return [
            ModelInfo(
                id=configured.id,
                name="API Model Name",
                max_input_length_auto_detected=256_000,
                max_tokens=32_768,
                supports_image=True,
            ),
        ]

    monkeypatch.setattr(OpenAIProvider, "fetch_models", fetch_models)

    result = await manager.discover_provider_models("openai")

    assert result.success is True
    assert configured.source == "builtin"
    assert configured.max_input_length_auto_detected == 256_000
    assert configured.max_tokens == 1024
    assert configured.supports_image is True
    assert provider.get_context_size(configured.id) == 256_000


def test_builtin_variants_do_not_share_model_instances(
    isolated_secret_dir,
) -> None:
    manager = ProviderManager()
    china = manager.get_provider("aliyun-tokenplan")
    international = manager.get_provider("aliyun-tokenplan-intl")

    assert china is not None
    assert international is not None
    assert china.models[0] is not international.models[0]

    original = international.models[0].max_tokens
    china.models[0].max_tokens = 4096

    assert international.models[0].max_tokens == original


async def test_discovery_preserves_model_config_overrides(
    isolated_secret_dir,
    monkeypatch,
) -> None:
    manager = ProviderManager()
    provider = manager.get_provider("openai")
    assert provider is not None
    provider.discovered_models = [
        ModelInfo(
            id="remote-model",
            name="Remote Model",
            source="discovered",
        ),
    ]
    provider.discovered_models[0].max_tokens = 1234
    provider.discovered_models[0].generate_kwargs = {"temperature": 0.2}
    provider.discovered_models[0].config_overrides = [
        "max_tokens",
        "generate_kwargs",
    ]

    async def fetch_models(_self, timeout=5):
        return [
            ModelInfo(
                id="remote-model",
                name="Updated Remote Model",
                max_tokens=8192,
                generate_kwargs={"temperature": 1},
            ),
        ]

    monkeypatch.setattr(OpenAIProvider, "fetch_models", fetch_models)

    result = await manager.discover_provider_models("openai")

    assert result.success is True
    model = provider.get_discovered_model_info("remote-model")
    assert model is not None
    assert model.name == "Updated Remote Model"
    assert model.max_tokens == 1234
    assert model.generate_kwargs == {"temperature": 0.2}
    assert set(model.config_overrides) >= {"max_tokens", "generate_kwargs"}


async def test_activate_provider_invalid_provider_raises(
    isolated_secret_dir,
) -> None:
    manager = ProviderManager()

    with pytest.raises(ProviderError, match="Provider 'missing' not found"):
        await manager.activate_model("missing", "gpt-5")


async def test_activate_provider_invalid_model_raises(
    isolated_secret_dir,
) -> None:
    manager = ProviderManager()

    with pytest.raises(ModelNotFoundException, match="not-exists"):
        await manager.activate_model("openai", "not-exists")


async def test_discovery_only_model_cannot_activate_until_added(
    isolated_secret_dir,
) -> None:
    manager = ProviderManager()
    provider = manager.get_provider("openai")
    assert provider is not None
    provider.discovered_models = [
        ModelInfo(id="candidate-only", name="Candidate", source="discovered"),
    ]

    with pytest.raises(ModelNotFoundException):
        await manager.activate_model("openai", "candidate-only")

    await manager.add_model_to_provider(
        "openai",
        ModelInfo(id="candidate-only", name="Candidate"),
    )
    await manager.activate_model("openai", "candidate-only")
    assert manager.active_model is not None
    assert manager.active_model.model == "candidate-only"


async def test_preview_discovery_does_not_invalidate_saved_refresh(
    isolated_secret_dir,
    monkeypatch,
) -> None:
    manager = ProviderManager()
    provider = manager.get_provider("openai")
    assert provider is not None
    first_started = asyncio.Event()
    release_first = asyncio.Event()
    call_count = 0

    async def fetch_models(_self, timeout=5):
        nonlocal call_count
        _ = timeout
        call_count += 1
        if call_count == 1:
            first_started.set()
            await release_first.wait()
            return [ModelInfo(id="saved-model", name="Saved")]
        return [ModelInfo(id="preview-model", name="Preview")]

    monkeypatch.setattr(OpenAIProvider, "fetch_models", fetch_models)
    saved_task = asyncio.create_task(
        manager.discover_provider_models("openai", save=True),
    )
    await first_started.wait()
    preview = await manager.discover_provider_models(
        "openai",
        save=False,
        provider_override=provider.model_copy(deep=True),
    )
    release_first.set()
    saved = await saved_task

    assert preview.models[0].id == "preview-model"
    assert saved.success is True
    assert provider.get_discovered_model_info("saved-model") is not None


async def test_plugin_discovery_and_check_update_fresh_provider_instance(
    isolated_secret_dir,
    monkeypatch,
) -> None:
    manager = ProviderManager()
    plugin_id = "plugin-openai"
    manager.plugin_providers[plugin_id] = {
        "info": ProviderInfo(
            id=plugin_id,
            name="Plugin OpenAI",
            base_url="https://plugin.example/v1",
            chat_model="OpenAIChatModel",
        ),
        "class": OpenAIProvider,
    }

    async def fetch_models(_self, timeout=5):
        _ = timeout
        return [ModelInfo(id="plugin-model", name="Plugin Model")]

    async def check_model_compatibility(_self, model_id, timeout=5):
        _ = model_id, timeout
        return provider_manager_module.ModelConnectionResult(
            success=True,
            supports_tool_calling=True,
        )

    monkeypatch.setattr(OpenAIProvider, "fetch_models", fetch_models)
    monkeypatch.setattr(
        OpenAIProvider,
        "check_model_compatibility",
        check_model_compatibility,
    )

    discovery = await manager.discover_provider_models(plugin_id)
    check = await manager.check_provider_model(plugin_id, "plugin-model")
    refreshed = manager.get_provider(plugin_id)

    assert discovery.success is True
    assert check.status == "available"
    assert refreshed is not None
    model = refreshed.get_discovered_model_info("plugin-model")
    assert model is not None
    assert model.availability_status == "available"
    assert model.supports_tool_calling is True


async def test_discovery_error_redacts_credentials_before_persisting(
    isolated_secret_dir,
    monkeypatch,
) -> None:
    manager = ProviderManager()

    async def fetch_models(_self, timeout=5):
        _ = timeout
        raise RuntimeError("api_key=discovery-secret")

    monkeypatch.setattr(OpenAIProvider, "fetch_models", fetch_models)

    result = await manager.discover_provider_models("openai")
    provider = manager.get_provider("openai")

    assert result.success is False
    assert "discovery-secret" not in result.error
    assert result.error == "api_key=[redacted]"
    assert provider is not None
    assert provider.models_last_sync_error == result.error


async def test_add_model_to_provider_duplicate_id_raises(
    isolated_secret_dir,
) -> None:
    manager = ProviderManager()
    model_info = ModelInfo(id="custom-duplicate", name="Custom Duplicate")

    provider = await manager.add_model_to_provider("openai", model_info)

    assert [m.id for m in provider.extra_models].count("custom-duplicate") == 1

    with pytest.raises(ProviderError, match="already exists"):
        await manager.add_model_to_provider("openai", model_info)

    reloaded = ProviderManager()
    reloaded_provider = reloaded.get_provider("openai")

    assert reloaded_provider is not None
    assert reloaded_provider.extra_models is not None
    assert [m.id for m in reloaded_provider.extra_models].count(
        "custom-duplicate",
    ) == 1


async def test_add_discovered_model_copies_catalog_metadata(
    isolated_secret_dir,
) -> None:
    manager = ProviderManager()
    original = manager.get_provider("openai")
    assert original is not None
    original.discovered_models = [
        ModelInfo(
            id="remote-candidate",
            name="Remote Candidate",
            source="discovered",
            max_input_length_auto_detected=256_000,
            max_tokens=16_384,
            is_free=True,
        ),
    ]

    info = await manager.add_model_to_provider(
        "openai",
        ModelInfo(id="remote-candidate", name="Remote Candidate"),
    )

    assert all(model.id != "remote-candidate" for model in info.models)
    added = next(
        model for model in info.extra_models if model.id == "remote-candidate"
    )
    assert added.source == "user"
    assert added.max_input_length_auto_detected == 256_000
    assert added.max_tokens == 16_384
    assert added.is_free is True


def test_model_check_classification() -> None:
    manager = ProviderManager.__new__(ProviderManager)

    denied = manager._classify_model_check(
        False,
        "API error (status=401): unauthorized",
    )
    assert denied.status == "permission_denied"
    assert denied.http_status == 401
    assert denied.retryable is False

    missing = manager._classify_model_check(
        False,
        "API error (status=404): model not found",
    )
    assert missing.status == "model_not_found"
    assert missing.retryable is False

    limited = manager._classify_model_check(
        False,
        "HTTP 429 rate limit exceeded",
    )
    assert limited.status == "rate_limited"
    assert limited.retryable is True

    temporary = manager._classify_model_check(False, "request timed out")
    assert temporary.status == "transient_error"
    assert temporary.retryable is True

    no_tools = manager._classify_model_check(
        False,
        "status=400: The tool call is not supported",
    )
    assert no_tools.status == "incompatible_api"
    assert no_tools.retryable is False


def test_legacy_available_model_requires_new_tool_check() -> None:
    model = ModelInfo.model_validate(
        {
            "id": "legacy-model",
            "name": "Legacy Model",
            "availability_status": "available",
        },
    )
    assert model.availability_status == "unverified"
    assert model.supports_tool_calling is None


async def test_kimi_discovery_merges_api_and_catalog(
    isolated_secret_dir,
    monkeypatch,
) -> None:
    manager = ProviderManager()
    provider = manager.get_provider("kimi-cn")
    assert provider is not None
    provider.discovered_models = []

    async def fetch_models(_self, timeout=5):
        _ = timeout
        return [
            ModelInfo(id="kimi-k2.6", name="Kimi K2.6"),
            ModelInfo(id="kimi-k2.5", name="Kimi K2.5"),
        ]

    monkeypatch.setattr(OpenAIProvider, "fetch_models", fetch_models)
    result = await manager.discover_provider_models("kimi-cn", save=False)

    by_id = {model.id: model for model in result.models}
    assert by_id["kimi-k2.6"].discovery_origin == "api"
    assert by_id["kimi-k2.5"].discovery_origin == "both"
    assert by_id["kimi-k2-thinking"].discovery_origin == "catalog"
    assert result.added_count == 2


async def test_rejects_unavailable_discovered_model(
    isolated_secret_dir,
) -> None:
    manager = ProviderManager()
    provider = manager.get_provider("openai")
    assert provider is not None
    provider.discovered_models = [
        ModelInfo(
            id="forbidden-model",
            name="Forbidden Model",
            source="discovered",
            availability_status="permission_denied",
            availability_message="status=401: unauthorized",
            availability_retryable=False,
        ),
    ]

    with pytest.raises(ProviderError, match="cannot be added"):
        await manager.add_model_to_provider(
            "openai",
            ModelInfo(id="forbidden-model", name="Forbidden Model"),
        )


async def test_rejects_activation_of_incompatible_model(
    isolated_secret_dir,
) -> None:
    manager = ProviderManager()
    provider = manager.get_provider("openai")
    assert provider is not None
    provider.extra_models = [
        ModelInfo(
            id="chat-only-model",
            name="Chat Only Model",
            source="user",
            availability_status="incompatible_api",
            availability_message="The tool call is not supported",
            availability_retryable=False,
        ),
    ]

    with pytest.raises(ProviderError, match="cannot be activated"):
        await manager.activate_model("openai", "chat-only-model")


def test_save_provider_skip_if_exists_does_not_overwrite(
    isolated_secret_dir,
) -> None:
    manager = ProviderManager()
    provider = OpenAIProvider(
        id="custom-skip",
        name="Original",
        api_key="sk-original",
    )
    manager._save_provider(provider, is_builtin=False)

    provider.name = "Changed"
    provider.api_key = "sk-changed"
    manager._save_provider(provider, is_builtin=False, skip_if_exists=True)

    loaded = manager.load_provider("custom-skip", is_builtin=False)
    assert loaded is not None
    assert loaded.name == "Original"
    assert loaded.api_key == "sk-original"


def test_load_provider_missing_returns_none(isolated_secret_dir) -> None:
    manager = ProviderManager()

    loaded = manager.load_provider("not-found", is_builtin=False)

    assert loaded is None


def test_provider_from_data_dispatch_to_anthropic(isolated_secret_dir) -> None:
    manager = ProviderManager()

    provider = manager._provider_from_data(
        {
            "id": "custom-anthropic",
            "name": "Custom Anthropic",
            "chat_model": "AnthropicChatModel",
            "api_key": "sk-ant-x",
        },
    )

    assert isinstance(provider, AnthropicProvider)


def test_provider_from_data_fallback_to_openai(isolated_secret_dir) -> None:
    manager = ProviderManager()

    provider = manager._provider_from_data(
        {
            "id": "custom-openai-like",
            "name": "OpenAI Like",
            "base_url": "https://custom.example/v1",
        },
    )

    assert isinstance(provider, OpenAIProvider)


def test_init_from_storage_migrates_with_different_provider(
    isolated_secret_dir,
) -> None:
    builtin_path = isolated_secret_dir / "providers" / "builtin"
    builtin_path.mkdir(parents=True, exist_ok=True)

    legacy_minimax_provider = {
        "id": "minimax",
        "name": "MiniMax",
        "base_url": "https://api.minimax.io/v1",
        "api_key": "sk-legacy-minimax",
        "chat_model": "OpenAIChatModel",
        "models": [{"id": "MiniMax-M2.5", "name": "MiniMax M2.5"}],
        "generate_kwargs": {"temperature": 1.0},
    }
    (builtin_path / "minimax.json").write_text(
        json.dumps(legacy_minimax_provider, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    manager = ProviderManager()

    provider = manager.get_provider("minimax")

    assert provider is not None
    assert isinstance(provider, AnthropicProvider)
    # url / name / chatmodel should be updated
    assert provider.base_url == "https://api.minimax.io/anthropic"
    assert provider.chat_model == "AnthropicChatModel"
    assert provider.name == "MiniMax (International)"
    # api key should be preserved
    assert provider.api_key == "sk-legacy-minimax"

    from agentscope.model import AnthropicChatModel

    assert provider.get_chat_model_cls() == AnthropicChatModel

    legacy_ollama_provider = {
        "id": "ollama",
        "name": "Ollama New",
        "base_url": "http://legacy-ollama:11434",
        "api_key": "sk-legacy-ollama",
        "chat_model": "OpenAIChatModel",
        "models": [],
    }
    (builtin_path / "ollama.json").write_text(
        json.dumps(legacy_ollama_provider, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    manager = ProviderManager()
    assert manager.get_provider("ollama") is not None
    assert (
        manager.get_provider("ollama").base_url == "http://legacy-ollama:11434"
    )


def test_provider_group_metadata(isolated_secret_dir) -> None:
    """Providers in the same brand share provider_group."""
    manager = ProviderManager()

    aliyun_ids = [
        "dashscope",
        "aliyun-codingplan",
        "aliyun-codingplan-intl",
        "aliyun-tokenplan",
    ]
    for pid in aliyun_ids:
        p = manager.get_provider(pid)
        assert p is not None, f"{pid} not found"
        assert p.provider_group == "aliyun"
        assert p.provider_group_name == "Aliyun"

    kimi_ids = ["kimi-cn", "kimi-intl", "kimi-codingplan"]
    for pid in kimi_ids:
        p = manager.get_provider(pid)
        assert p is not None, f"{pid} not found"
        assert p.provider_group == "kimi"

    volcengine_ids = ["volcengine-cn", "volcengine-cn-codingplan"]
    for pid in volcengine_ids:
        p = manager.get_provider(pid)
        assert p is not None, f"{pid} not found"
        assert p.provider_group == "volcengine"


async def test_provider_group_in_get_info(isolated_secret_dir) -> None:
    """get_info() should include provider_group fields."""
    manager = ProviderManager()
    provider = manager.get_provider("dashscope")
    assert provider is not None

    info = await provider.get_info()
    assert info.provider_group == "aliyun"
    assert info.provider_group_name == "Aliyun"
    assert info.provider_variant == "dashscope"


def test_dashscope_max_inline_media_bytes_loaded_from_json(
    isolated_secret_dir,
) -> None:
    """A user-set ``max_inline_media_bytes`` in dashscope.json must be
    loaded by ``_init_from_storage`` and actually used by the capping
    formatter at runtime.

    Writes a builtin dashscope.json with a custom threshold, boots a fresh
    ``ProviderManager`` (which runs ``_init_from_storage``), and asserts
    the runtime builtin instance — not just the freshly deserialized one —
    carries the value through to the formatter.
    """
    builtin_path = isolated_secret_dir / "providers" / "builtin"
    builtin_path.mkdir(parents=True, exist_ok=True)

    dashscope_json = {
        "id": "dashscope",
        "name": "DashScope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "sk-test",
        "chat_model": "DashScopeChatModel",
        "models": [{"id": "qwen3-max", "name": "Qwen3 Max"}],
        "max_inline_media_bytes": 4096,
    }
    (builtin_path / "dashscope.json").write_text(
        json.dumps(dashscope_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    manager = ProviderManager()

    provider = manager.get_provider("dashscope")
    assert provider is not None
    # The runtime builtin must reflect the value loaded from disk, not the
    # field default (2 MB).
    assert provider.max_inline_media_bytes == 4096

    # And it must reach the capping formatter that actually guards requests.
    model = provider.get_chat_model_instance("qwen3-max")
    assert model.formatter.max_bytes == 4096


def test_dashscope_max_inline_media_bytes_defaults_when_absent(
    isolated_secret_dir,
) -> None:
    """An existing dashscope.json without the new key must fall back to the
    built-in default (2 MB) — i.e. upgrading must not silently cap at 0."""
    builtin_path = isolated_secret_dir / "providers" / "builtin"
    builtin_path.mkdir(parents=True, exist_ok=True)

    # Legacy JSON: no max_inline_media_bytes key at all.
    dashscope_json = {
        "id": "dashscope",
        "name": "DashScope",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "api_key": "sk-test",
        "chat_model": "DashScopeChatModel",
        "models": [{"id": "qwen3-max", "name": "Qwen3 Max"}],
    }
    (builtin_path / "dashscope.json").write_text(
        json.dumps(dashscope_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    manager = ProviderManager()
    provider = manager.get_provider("dashscope")
    assert provider is not None
    assert provider.max_inline_media_bytes == 2 * 1024 * 1024
    assert (
        provider.get_chat_model_instance("qwen3-max").formatter.max_bytes
        == 2 * 1024 * 1024
    )


# ---------------------------------------------------------------------------
# Inline-media capping for the other providers (OpenAI / Anthropic / Gemini).
# Same oversized-request bug as DashScope: their agentscope formatters read
# every file:// media off disk and base64-inline the whole file on every
# call. Each provider now wires a shared capping formatter and exposes the
# same configurable ``max_inline_media_bytes`` field, restored by
# ``_init_from_storage`` via the generic ``hasattr`` branch.
# ---------------------------------------------------------------------------

# (provider_id, chat_model, model_id, capping_formatter_cls)
_CAPPING_PROVIDER_CASES = [
    ("openai", "OpenAIChatModel", "gpt-4o", _CappingOpenAIFormatter),
    (
        "anthropic",
        "AnthropicChatModel",
        "claude-3-5-sonnet",
        _CappingAnthropicFormatter,
    ),
    (
        "gemini",
        "GeminiChatModel",
        "gemini-2.0-flash",
        _CappingGeminiFormatter,
    ),
]


def _write_builtin_provider_json(
    isolated_secret_dir,
    provider_id: str,
    chat_model: str,
    model_id: str,
    *,
    with_cap: bool,
) -> None:
    """Write a builtin <id>.json under providers/builtin/.

    ``with_cap=True`` sets a 4096-byte ``max_inline_media_bytes``;
    ``False`` omits the key (legacy JSON) to exercise the default fallback.
    """
    builtin_path = isolated_secret_dir / "providers" / "builtin"
    builtin_path.mkdir(parents=True, exist_ok=True)

    data = {
        "id": provider_id,
        "name": provider_id.title(),
        "base_url": "https://example.test/v1",
        "api_key": "sk-test",
        "chat_model": chat_model,
        "models": [{"id": model_id, "name": model_id}],
    }
    if with_cap:
        data["max_inline_media_bytes"] = 4096
    (builtin_path / f"{provider_id}.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


@pytest.mark.parametrize(
    "provider_id,chat_model,model_id,formatter_cls",
    _CAPPING_PROVIDER_CASES,
)
def test_max_inline_media_bytes_loaded_from_json(
    isolated_secret_dir,
    provider_id,
    chat_model,
    model_id,
    formatter_cls,
) -> None:
    """A user-set ``max_inline_media_bytes`` in <id>.json must be loaded by
    ``_init_from_storage`` and reach the runtime capping formatter."""
    _write_builtin_provider_json(
        isolated_secret_dir,
        provider_id,
        chat_model,
        model_id,
        with_cap=True,
    )

    manager = ProviderManager()
    provider = manager.get_provider(provider_id)
    assert provider is not None
    # Runtime builtin reflects the disk value, not the 2 MB default.
    assert provider.max_inline_media_bytes == 4096

    model = provider.get_chat_model_instance(model_id)
    assert isinstance(model.formatter, formatter_cls)
    assert model.formatter.max_bytes == 4096


@pytest.mark.parametrize(
    "provider_id,chat_model,model_id,formatter_cls",
    _CAPPING_PROVIDER_CASES,
)
def test_max_inline_media_bytes_defaults_when_absent(
    isolated_secret_dir,
    provider_id,
    chat_model,
    model_id,
    formatter_cls,
) -> None:
    """A legacy <id>.json without the key falls back to the 2 MB default
    (upgrading must not silently cap at 0)."""
    _write_builtin_provider_json(
        isolated_secret_dir,
        provider_id,
        chat_model,
        model_id,
        with_cap=False,
    )

    manager = ProviderManager()
    provider = manager.get_provider(provider_id)
    assert provider is not None
    assert provider.max_inline_media_bytes == 2 * 1024 * 1024

    model = provider.get_chat_model_instance(model_id)
    assert isinstance(model.formatter, formatter_cls)
    assert model.formatter.max_bytes == 2 * 1024 * 1024


async def test_github_models_provider_uses_new_endpoint_and_prefixes(
    isolated_secret_dir,
) -> None:
    manager = ProviderManager()
    provider = manager.get_provider("github-models")

    assert provider is not None
    assert isinstance(provider, OpenAIProvider)
    assert isinstance(provider, GitHubModelsProvider)
    assert provider.base_url == "https://models.github.ai/inference"
    assert provider.freeze_url is False
    assert provider.api_key_prefix == "ghp_"
    assert provider.api_key_prefixes == ["ghp_", "github_pat_"]

    info = await provider.get_info()
    assert info.base_url == "https://models.github.ai/inference"
    assert info.freeze_url is False
    assert info.api_key_prefix == "ghp_"
    assert info.api_key_prefixes == ["ghp_", "github_pat_"]


async def test_update_config_persists_api_key_prefixes(
    isolated_secret_dir,
) -> None:
    manager = ProviderManager()
    provider = manager.get_provider("github-models")
    assert provider is not None

    manager.update_provider(
        "github-models",
        {"api_key_prefixes": ["ghp_", "github_pat_"]},
    )

    provider = manager.get_provider("github-models")
    assert provider.api_key_prefixes == ["ghp_", "github_pat_"]
    info = await provider.get_info()
    assert info.api_key_prefixes == ["ghp_", "github_pat_"]
