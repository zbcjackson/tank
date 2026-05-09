"""Model capability detection — what modalities can the configured LLM accept?

Tank's multi-modal pipeline (phases 2+) wants to know at upload time
whether the user's currently-configured LLM can actually consume an
image/PDF/audio input. This module resolves that once at startup,
stores the answer, and exposes it to the HTTP layer so the web client
can pre-filter file drops before bytes leave the browser.

Three sources, in order of authority:

1. **Config override** (``LLMProfile.capabilities``): user declares what
   the model supports in ``config.yaml``. Always wins. Use this when
   pointing at a local/custom endpoint the detector can't recognise.
2. **Provider API probe** (OpenRouter today): authoritative data when
   available. Silently skipped on non-OpenRouter endpoints and on any
   network failure.
3. **Pattern match on model id**: a hardcoded table of known model
   families. Covers Gemini, Claude, GPT-4o/5, Llama-Vision, Qwen-VL.
   Unknown models default to text-only (safe).

The registry is resolved once at startup and never refreshed — config
is immutable until the server restarts, and so is ``LLMProfile.model``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

import httpx

from ..core.content import (
    MODALITY_AUDIO,
    MODALITY_FILE,
    MODALITY_IMAGE,
    MODALITY_TEXT,
    MODALITY_VIDEO,
)
from .model_table import registry

if TYPE_CHECKING:
    from .profile import LLMProfile

logger = logging.getLogger(__name__)


class CapabilitySource(str, Enum):
    """How a ModelCapabilities was obtained. Useful for log/UX clarity."""

    CONFIG_OVERRIDE = "config_override"
    PROVIDER_API = "provider_api"
    MODEL_REGISTRY = "model_registry"
    PATTERN_MATCH = "pattern_match"
    FALLBACK_TEXT = "fallback_text"


@dataclass(frozen=True, slots=True)
class ModelCapabilities:
    """What modalities a model can consume as input."""

    model_id: str
    input_modalities: frozenset[str]
    source: CapabilitySource

    def supports(self, modality: str) -> bool:
        return modality in self.input_modalities


# ---------------------------------------------------------------------------
# Pattern table
# ---------------------------------------------------------------------------

# Ordered: more specific patterns first. The first match wins.
# Lift straight from publicly documented model pages; when in doubt,
# err toward the smaller capability set.
_PATTERNS: tuple[tuple[re.Pattern[str], frozenset[str]], ...] = (
    # Gemini 1.5+ — text, image, file (PDF), audio, video
    (
        re.compile(r"gemini-(3|2\.5|2|1\.5)"),
        frozenset({
            MODALITY_TEXT,
            MODALITY_IMAGE,
            MODALITY_FILE,
            MODALITY_AUDIO,
            MODALITY_VIDEO,
        }),
    ),
    # Gemini 1.0 — text + image only
    (
        re.compile(r"gemini-1\.0"),
        frozenset({MODALITY_TEXT, MODALITY_IMAGE}),
    ),
    # Claude 3.x / 4.x / opus-4 — text, image, file
    (
        re.compile(r"claude-(opus-4|sonnet-4|haiku-4|3\.7|3\.5|3)"),
        frozenset({MODALITY_TEXT, MODALITY_IMAGE, MODALITY_FILE}),
    ),
    # Older Claude — text only
    (
        re.compile(r"claude-(2|instant)"),
        frozenset({MODALITY_TEXT}),
    ),
    # GPT-4o (vision + file) — check before bare "gpt-4"
    (
        re.compile(r"gpt-4o"),
        frozenset({MODALITY_TEXT, MODALITY_IMAGE, MODALITY_FILE}),
    ),
    # GPT-5, GPT-4.1 — text + image + file
    (
        re.compile(r"gpt-(5|4\.1)"),
        frozenset({MODALITY_TEXT, MODALITY_IMAGE, MODALITY_FILE}),
    ),
    # Older explicit vision variants
    (
        re.compile(r"gpt-4-(vision|turbo)"),
        frozenset({MODALITY_TEXT, MODALITY_IMAGE}),
    ),
    # Plain gpt-4/gpt-3 (non-vision) — text only
    (
        re.compile(r"gpt-(3|4(?!-|o|\.))"),
        frozenset({MODALITY_TEXT}),
    ),
    # Llama vision variants
    (
        re.compile(r"llama-(3\.[234]-vision|4)"),
        frozenset({MODALITY_TEXT, MODALITY_IMAGE}),
    ),
    # Qwen vision + audio
    (
        re.compile(r"qwen.*-(vl|audio)"),
        frozenset({MODALITY_TEXT, MODALITY_IMAGE, MODALITY_AUDIO}),
    ),
)


def _pattern_match(model_id: str) -> ModelCapabilities:
    """Classify a model by its id using :data:`_PATTERNS`.

    Unknown models fall back to text-only — the safe default. The user
    can override via ``capabilities:`` in ``config.yaml`` when they
    know the model supports more.
    """
    lower = model_id.lower()
    for pattern, modalities in _PATTERNS:
        if pattern.search(lower):
            return ModelCapabilities(
                model_id=model_id,
                input_modalities=modalities,
                source=CapabilitySource.PATTERN_MATCH,
            )
    return ModelCapabilities(
        model_id=model_id,
        input_modalities=frozenset({MODALITY_TEXT}),
        source=CapabilitySource.FALLBACK_TEXT,
    )


def _registry_lookup(model_id: str) -> ModelCapabilities | None:
    """Consult the bundled LiteLLM snapshot.

    Returns ``None`` when the model isn't in the table — caller falls
    through to pattern matching. Modalities from the registry are
    authoritative: they come from LiteLLM's hand-curated per-model
    flags, not from our regex guesses.
    """
    record = registry().lookup(model_id)
    if record is None:
        return None
    if not record.modalities:
        return None
    return ModelCapabilities(
        model_id=model_id,
        input_modalities=record.modalities,
        source=CapabilitySource.MODEL_REGISTRY,
    )


# ---------------------------------------------------------------------------
# OpenRouter probe
# ---------------------------------------------------------------------------

# Modalities OpenRouter reports. Map to Tank's canonical names.
_OPENROUTER_MODALITY_MAP = {
    "text": MODALITY_TEXT,
    "image": MODALITY_IMAGE,
    "file": MODALITY_FILE,
    "audio": MODALITY_AUDIO,
    "video": MODALITY_VIDEO,
}


def _is_openrouter(base_url: str) -> bool:
    return "openrouter.ai" in base_url.lower()


async def _probe_openrouter(profile: LLMProfile) -> ModelCapabilities | None:
    """Query OpenRouter's /models endpoint for the model's modalities.

    Returns ``None`` on any failure (network, missing data, parse
    error) — the caller falls back to pattern matching. We never
    raise: a bad probe must not crash startup.
    """
    url = profile.base_url.rstrip("/") + "/models"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {profile.api_key}"},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.debug("OpenRouter capability probe failed: %s", exc)
        return None

    entries = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        return None

    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("id") != profile.model:
            continue
        arch = entry.get("architecture") or {}
        raw_mods = arch.get("input_modalities") or []
        if not isinstance(raw_mods, list):
            return None
        mapped = {
            _OPENROUTER_MODALITY_MAP[m]
            for m in raw_mods
            if m in _OPENROUTER_MODALITY_MAP
        }
        if not mapped:
            return None
        return ModelCapabilities(
            model_id=profile.model,
            input_modalities=frozenset(mapped),
            source=CapabilitySource.PROVIDER_API,
        )
    return None


# ---------------------------------------------------------------------------
# Top-level resolver
# ---------------------------------------------------------------------------


async def resolve_capabilities(profile: LLMProfile) -> ModelCapabilities:
    """Resolve a model's input modalities (async; may probe the network).

    Authority order: config override → provider API probe → bundled
    registry → pattern match → text-only fallback. Always returns a
    value; never raises.
    """
    if profile.capabilities:
        return ModelCapabilities(
            model_id=profile.model,
            input_modalities=frozenset(profile.capabilities),
            source=CapabilitySource.CONFIG_OVERRIDE,
        )

    if _is_openrouter(profile.base_url):
        probed = await _probe_openrouter(profile)
        if probed is not None:
            return probed

    registry_hit = _registry_lookup(profile.model)
    if registry_hit is not None:
        return registry_hit

    return _pattern_match(profile.model)


def resolve_capabilities_sync(profile: LLMProfile) -> ModelCapabilities:
    """Resolve capabilities without any network call.

    Used during synchronous startup (``Assistant.__init__``). Skips the
    OpenRouter probe; config override, bundled registry, and pattern
    match still run. Callers that want the API-backed result should
    switch to :func:`resolve_capabilities` from an async context.
    """
    if profile.capabilities:
        return ModelCapabilities(
            model_id=profile.model,
            input_modalities=frozenset(profile.capabilities),
            source=CapabilitySource.CONFIG_OVERRIDE,
        )
    registry_hit = _registry_lookup(profile.model)
    if registry_hit is not None:
        return registry_hit
    return _pattern_match(profile.model)
