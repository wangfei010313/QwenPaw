# -*- coding: utf-8 -*-
# pylint: disable=protected-access,missing-function-docstring
"""Tests for update_model_config handling of max_input_length "auto" mode."""

from qwenpaw.providers.context_windows import DEFAULT_CONTEXT_WINDOW
from qwenpaw.providers.provider import ModelInfo, Provider


class _MutableCatalogProvider:
    """Minimal stand-in exposing update_model_config and get_context_size."""

    models: list[ModelInfo]
    extra_models: list[ModelInfo]

    update_model_config = Provider.update_model_config
    get_context_size = Provider.get_context_size
    _get_context_size = Provider._get_context_size
    _context_catalog_enabled = Provider._context_catalog_enabled

    def get_model_info(self, model_id):
        for model in self.models + self.extra_models:
            if model.id == model_id:
                return model
        return None


def _make_provider() -> _MutableCatalogProvider:
    p = _MutableCatalogProvider()
    model = ModelInfo(
        id="claude-sonnet-4-5",
        name="Claude Sonnet 4.5",
        max_input_length=200_000,
    )
    p.models = [model]
    p.extra_models = []
    return p


# ---------------------------------------------------------------------------
# update_model_config with "auto"
# ---------------------------------------------------------------------------


def test_auto_mode_sets_max_input_length_to_none():
    p = _make_provider()
    assert p.update_model_config(
        "claude-sonnet-4-5",
        {"max_input_length": "auto"},
    )
    model = p.get_model_info("claude-sonnet-4-5")
    assert model.max_input_length is None
    assert model.max_input_length_configured is False


def test_auto_mode_resets_context_length_from_api():
    p = _make_provider()
    # Pre-set a cached API probe result
    p.models[0].context_length_from_api = 500_000

    assert p.update_model_config(
        "claude-sonnet-4-5",
        {"max_input_length": "auto"},
    )
    model = p.get_model_info("claude-sonnet-4-5")
    assert model.context_length_from_api is None


def test_auto_mode_then_context_size_uses_catalog():
    """After switching to auto (no probe yet), catalog should apply."""
    p = _make_provider()
    p.update_model_config(
        "claude-sonnet-4-5",
        {"max_input_length": "auto"},
    )
    # No API probe yet — fall back to catalog
    assert p.get_context_size("claude-sonnet-4-5") == 200_000


def test_auto_mode_then_context_size_uses_probe():
    """After switching to auto and probe runs, probe result wins."""
    p = _make_provider()
    p.update_model_config(
        "claude-sonnet-4-5",
        {"max_input_length": "auto"},
    )
    # Simulate API probe result
    p.models[0].context_length_from_api = 500_000
    assert p.get_context_size("claude-sonnet-4-5") == 500_000


def test_explicit_value_overrides_auto():
    p = _make_provider()
    # First set auto
    p.update_model_config(
        "claude-sonnet-4-5",
        {"max_input_length": "auto"},
    )
    # Then set explicit value
    p.update_model_config(
        "claude-sonnet-4-5",
        {"max_input_length": 1_000_000},
    )
    model = p.get_model_info("claude-sonnet-4-5")
    assert model.max_input_length == 1_000_000
    assert model.max_input_length_configured is True
    assert p.get_context_size("claude-sonnet-4-5") == 1_000_000


def test_explicit_default_value_still_wins():
    p = _make_provider()
    # Set explicit 128k default
    p.update_model_config(
        "claude-sonnet-4-5",
        {"max_input_length": DEFAULT_CONTEXT_WINDOW},
    )
    model = p.get_model_info("claude-sonnet-4-5")
    assert model.max_input_length == DEFAULT_CONTEXT_WINDOW
    assert model.max_input_length_configured is True
    assert p.get_context_size("claude-sonnet-4-5") == DEFAULT_CONTEXT_WINDOW


def test_auto_switches_back_to_explicit():
    p = _make_provider()
    # Start explicit
    p.update_model_config(
        "claude-sonnet-4-5",
        {"max_input_length": 1_000_000},
    )
    assert p.get_context_size("claude-sonnet-4-5") == 1_000_000

    # Switch to auto
    p.update_model_config(
        "claude-sonnet-4-5",
        {"max_input_length": "auto"},
    )
    # No probe → catalog
    assert p.get_context_size("claude-sonnet-4-5") == 200_000

    # Switch back to explicit
    p.update_model_config(
        "claude-sonnet-4-5",
        {"max_input_length": 500_000},
    )
    assert p.get_context_size("claude-sonnet-4-5") == 500_000


def test_non_existent_model_returns_false():
    p = _make_provider()
    assert not p.update_model_config(
        "non-existent",
        {"max_input_length": "auto"},
    )