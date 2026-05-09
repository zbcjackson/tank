"""Tests for the model capability detection module."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from tank_backend.core.content import (
    MODALITY_AUDIO,
    MODALITY_FILE,
    MODALITY_IMAGE,
    MODALITY_TEXT,
    MODALITY_VIDEO,
)
from tank_backend.llm.capabilities import (
    CapabilitySource,
    ModelCapabilities,
    _pattern_match,
    resolve_capabilities,
    resolve_capabilities_sync,
)
from tank_backend.llm.profile import LLMProfile


def _profile(
    model: str,
    *,
    base_url: str = "https://api.openai.com/v1",
    capabilities: frozenset[str] = frozenset(),
) -> LLMProfile:
    return LLMProfile(
        name="default",
        api_key="sk-test",
        model=model,
        base_url=base_url,
        capabilities=capabilities,
    )


class TestPatternMatch:
    """Test the hardcoded model-id → modalities table."""

    @pytest.mark.parametrize(
        ("model", "expected"),
        [
            # Gemini 1.5+ — full multi-modal
            ("gemini-2.5-flash", {
                MODALITY_TEXT, MODALITY_IMAGE, MODALITY_FILE,
                MODALITY_AUDIO, MODALITY_VIDEO,
            }),
            ("gemini-3.1-flash-lite", {
                MODALITY_TEXT, MODALITY_IMAGE, MODALITY_FILE,
                MODALITY_AUDIO, MODALITY_VIDEO,
            }),
            ("gemini-1.5-pro", {
                MODALITY_TEXT, MODALITY_IMAGE, MODALITY_FILE,
                MODALITY_AUDIO, MODALITY_VIDEO,
            }),
            # Gemini 1.0 — text + image only
            ("gemini-1.0-pro", {MODALITY_TEXT, MODALITY_IMAGE}),
            # Claude — text + image + file
            ("claude-opus-4-20260101", {
                MODALITY_TEXT, MODALITY_IMAGE, MODALITY_FILE,
            }),
            ("claude-3.5-sonnet", {
                MODALITY_TEXT, MODALITY_IMAGE, MODALITY_FILE,
            }),
            ("claude-3-haiku", {
                MODALITY_TEXT, MODALITY_IMAGE, MODALITY_FILE,
            }),
            # Older Claude — text only
            ("claude-2.1", {MODALITY_TEXT}),
            ("claude-instant-1", {MODALITY_TEXT}),
            # GPT-4o — text + image + file
            ("gpt-4o", {MODALITY_TEXT, MODALITY_IMAGE, MODALITY_FILE}),
            ("gpt-4o-mini", {MODALITY_TEXT, MODALITY_IMAGE, MODALITY_FILE}),
            # GPT-5 / GPT-4.1
            ("gpt-5", {MODALITY_TEXT, MODALITY_IMAGE, MODALITY_FILE}),
            ("gpt-4.1-preview", {
                MODALITY_TEXT, MODALITY_IMAGE, MODALITY_FILE,
            }),
            # Older vision variants
            ("gpt-4-vision-preview", {MODALITY_TEXT, MODALITY_IMAGE}),
            ("gpt-4-turbo", {MODALITY_TEXT, MODALITY_IMAGE}),
            # Plain gpt-4 / gpt-3 — text only
            ("gpt-4", {MODALITY_TEXT}),
            ("gpt-3.5-turbo", {MODALITY_TEXT}),
            # Llama vision
            ("llama-3.2-vision-11b", {MODALITY_TEXT, MODALITY_IMAGE}),
            ("llama-4-scout", {MODALITY_TEXT, MODALITY_IMAGE}),
            # Qwen
            ("qwen2-vl-72b", {MODALITY_TEXT, MODALITY_IMAGE, MODALITY_AUDIO}),
            ("qwen2-audio-7b", {MODALITY_TEXT, MODALITY_IMAGE, MODALITY_AUDIO}),
        ],
    )
    def test_known_patterns(self, model: str, expected: set[str]):
        caps = _pattern_match(model)
        assert caps.input_modalities == frozenset(expected)
        assert caps.source == CapabilitySource.PATTERN_MATCH
        assert caps.model_id == model

    def test_unknown_model_falls_back_to_text(self):
        caps = _pattern_match("unknown-model-xyz")
        assert caps.input_modalities == frozenset({MODALITY_TEXT})
        assert caps.source == CapabilitySource.FALLBACK_TEXT

    def test_case_insensitive_matching(self):
        # Model id lookups are lower-cased before pattern matching.
        caps = _pattern_match("GPT-4o")
        assert MODALITY_IMAGE in caps.input_modalities


class TestConfigOverride:
    """Config-declared capabilities always win."""

    @pytest.mark.asyncio()
    async def test_override_wins_over_pattern(self):
        # Model id would pattern-match to text-only; override forces images.
        profile = _profile(
            "unknown-custom-model",
            capabilities=frozenset({MODALITY_TEXT, MODALITY_IMAGE}),
        )
        caps = await resolve_capabilities(profile)
        assert caps.input_modalities == frozenset(
            {MODALITY_TEXT, MODALITY_IMAGE}
        )
        assert caps.source == CapabilitySource.CONFIG_OVERRIDE

    def test_sync_override_wins(self):
        profile = _profile(
            "gpt-4o",
            capabilities=frozenset({MODALITY_TEXT}),  # force downgrade
        )
        caps = resolve_capabilities_sync(profile)
        assert caps.input_modalities == frozenset({MODALITY_TEXT})
        assert caps.source == CapabilitySource.CONFIG_OVERRIDE


class TestSyncResolver:
    """resolve_capabilities_sync runs no network IO."""

    def test_known_model_hits_registry(self):
        """A model present in the bundled registry uses that source."""
        profile = _profile("gpt-4o")
        caps = resolve_capabilities_sync(profile)
        assert caps.source == CapabilitySource.MODEL_REGISTRY
        assert MODALITY_IMAGE in caps.input_modalities

    def test_provider_prefixed_model_hits_registry(self):
        """openai/gpt-4o resolves via suffix match to the gpt-4o row."""
        profile = _profile("openai/gpt-4o")
        caps = resolve_capabilities_sync(profile)
        assert caps.source == CapabilitySource.MODEL_REGISTRY
        assert MODALITY_IMAGE in caps.input_modalities

    def test_unknown_model_text_only(self):
        """Model absent from registry AND patterns — fallback to text."""
        profile = _profile("fictional-model-99-nobody-has-heard-of")
        caps = resolve_capabilities_sync(profile)
        assert caps.source == CapabilitySource.FALLBACK_TEXT
        assert caps.input_modalities == frozenset({MODALITY_TEXT})


class TestOpenRouterProbe:
    """The async resolver probes OpenRouter when base_url matches."""

    @pytest.mark.asyncio()
    async def test_openrouter_probe_populates_from_api(self):
        profile = _profile(
            "google/gemini-3.1-flash-lite",
            base_url="https://openrouter.ai/api/v1",
        )
        fake_response = {
            "data": [
                {
                    "id": "google/gemini-3.1-flash-lite",
                    "architecture": {
                        "input_modalities": [
                            "text", "image", "video", "file", "audio",
                        ],
                    },
                },
                {
                    "id": "other/model",
                    "architecture": {"input_modalities": ["text"]},
                },
            ]
        }

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_response = AsyncMock()
        mock_response.raise_for_status = lambda: None
        mock_response.json = lambda: fake_response
        mock_client.get.return_value = mock_response

        with patch("tank_backend.llm.capabilities.httpx.AsyncClient",
                   return_value=mock_client):
            caps = await resolve_capabilities(profile)

        assert caps.source == CapabilitySource.PROVIDER_API
        assert caps.input_modalities == frozenset({
            MODALITY_TEXT, MODALITY_IMAGE, MODALITY_FILE,
            MODALITY_AUDIO, MODALITY_VIDEO,
        })

    @pytest.mark.asyncio()
    async def test_openrouter_probe_failure_falls_back_to_pattern(self):
        """Network failure during probe must not crash; fall back to pattern."""
        profile = _profile(
            "google/gemini-1.5-pro",
            base_url="https://openrouter.ai/api/v1",
        )

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_client.get.side_effect = RuntimeError("network down")

        with patch("tank_backend.llm.capabilities.httpx.AsyncClient",
                   return_value=mock_client):
            caps = await resolve_capabilities(profile)

        # Pattern match on "gemini-1.5" still works.
        assert caps.source == CapabilitySource.PATTERN_MATCH
        assert MODALITY_VIDEO in caps.input_modalities

    @pytest.mark.asyncio()
    async def test_openrouter_probe_missing_model_falls_back(self):
        """When API returns models but not ours, fall back to pattern."""
        profile = _profile(
            "custom/nowhere-model",
            base_url="https://openrouter.ai/api/v1",
        )

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.__aexit__.return_value = None
        mock_response = AsyncMock()
        mock_response.raise_for_status = lambda: None
        mock_response.json = lambda: {"data": [
            {"id": "other/model", "architecture": {"input_modalities": ["text"]}}
        ]}
        mock_client.get.return_value = mock_response

        with patch("tank_backend.llm.capabilities.httpx.AsyncClient",
                   return_value=mock_client):
            caps = await resolve_capabilities(profile)

        # Unknown custom model → text-only fallback.
        assert caps.source == CapabilitySource.FALLBACK_TEXT

    @pytest.mark.asyncio()
    async def test_non_openrouter_skips_probe(self):
        """Non-OpenRouter base_url should skip probe entirely."""
        profile = _profile(
            "gpt-4o",
            base_url="https://api.openai.com/v1",
        )
        with patch("tank_backend.llm.capabilities._probe_openrouter") as probe:
            caps = await resolve_capabilities(profile)
        probe.assert_not_called()
        # gpt-4o is in the bundled registry → registry wins over patterns.
        assert caps.source == CapabilitySource.MODEL_REGISTRY


class TestModelCapabilitiesAPI:
    """Surface properties of the ModelCapabilities dataclass."""

    def test_supports(self):
        caps = ModelCapabilities(
            model_id="x",
            input_modalities=frozenset({MODALITY_TEXT, MODALITY_IMAGE}),
            source=CapabilitySource.PATTERN_MATCH,
        )
        assert caps.supports(MODALITY_TEXT)
        assert caps.supports(MODALITY_IMAGE)
        assert not caps.supports(MODALITY_VIDEO)
        assert not caps.supports(MODALITY_AUDIO)

    def test_is_frozen(self):
        from dataclasses import FrozenInstanceError

        caps = ModelCapabilities(
            model_id="x",
            input_modalities=frozenset({MODALITY_TEXT}),
            source=CapabilitySource.FALLBACK_TEXT,
        )
        with pytest.raises(FrozenInstanceError):
            caps.model_id = "y"  # type: ignore[misc]
