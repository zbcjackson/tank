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
    extra_body: dict[str, Any] = field(default_factory=dict)


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

    optional: dict[str, Any] = {}
    if "temperature" in raw:
        optional["temperature"] = float(raw["temperature"])
    if "max_tokens" in raw:
        optional["max_tokens"] = int(raw["max_tokens"])
    if "extra_headers" in raw and raw["extra_headers"]:
        optional["extra_headers"] = dict(raw["extra_headers"])
    if "stream_options" in raw:
        optional["stream_options"] = bool(raw["stream_options"])
    if "extra_body" in raw and raw["extra_body"]:
        optional["extra_body"] = dict(raw["extra_body"])

    return LLMProfile(
        name=name,
        api_key=api_key,
        model=model,
        base_url=base_url,
        **optional,
    )


def create_llm_from_profile(profile: LLMProfile) -> LLM:
    """Create an LLM instance from a resolved profile."""
    return LLM(
        api_key=profile.api_key,
        model=profile.model,
        base_url=profile.base_url,
        temperature=profile.temperature,
        max_tokens=profile.max_tokens,
        extra_headers=profile.extra_headers,
        stream_options=profile.stream_options,
        extra_body=profile.extra_body,
    )
