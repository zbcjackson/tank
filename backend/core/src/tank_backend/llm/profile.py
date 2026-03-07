"""LLM named profile: dataclass + factory."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .llm import LLM


@dataclass(frozen=True)
class LLMProfile:
    """Immutable configuration for a single LLM provider profile."""

    name: str
    api_key: str
    model: str
    base_url: str
    temperature: float = 0.7
    max_tokens: int = 10000
    extra_headers: dict[str, str] = field(default_factory=dict)
    stream_options: bool = True


def resolve_profile(name: str, raw: dict[str, Any]) -> LLMProfile:
    """Validate a raw YAML dict and build an LLMProfile.

    Environment variable interpolation (``${VAR}``) is handled by the YAML
    loader in ``AppConfig``, so values arrive here already resolved.

    Args:
        name: Profile name (e.g. "default").
        raw: Dict parsed from the YAML ``llm.<name>`` section.

    Raises:
        ValueError: On missing required fields.
    """
    api_key = raw.get("api_key")
    if not api_key:
        raise ValueError(f"LLM profile '{name}': missing or empty 'api_key'")

    model = raw.get("model")
    if not model:
        raise ValueError(f"LLM profile '{name}': missing 'model'")

    base_url = raw.get("base_url")
    if not base_url:
        raise ValueError(f"LLM profile '{name}': missing 'base_url'")

    return LLMProfile(
        name=name,
        api_key=api_key,
        model=model,
        base_url=base_url,
        temperature=float(raw.get("temperature", 0.7)),
        max_tokens=int(raw.get("max_tokens", 10000)),
        extra_headers=dict(raw.get("extra_headers") or {}),
        stream_options=bool(raw.get("stream_options", True)),
    )


def create_llm_from_profile(profile: LLMProfile) -> LLM:
    """Create an LLM instance from a resolved profile."""
    return LLM(
        api_key=profile.api_key,
        model=profile.model,
        base_url=profile.base_url,
        extra_headers=profile.extra_headers or None,
        stream_options=profile.stream_options,
    )
