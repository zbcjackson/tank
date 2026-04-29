"""Strongly-typed, validated application configuration.

Replaces the old ``plugin.config.AppConfig`` which returned raw dicts.
All config.yaml sections are parsed into frozen dataclasses at startup.
If ``AppConfig.load()`` succeeds, the entire config is valid.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..llm.profile import LLMProfile, resolve_profile
from .models import (
    AgentsConfig,
    AlertingConfig,
    AssistantConfig,
    AuditConfig,
    BrainConfig,
    CommandSecurityConfig,
    ContextConfig,
    EchoGuardConfig,
    FileAccessConfig,
    HealthMonitorConfig,
    JobsConfig,
    MemoryConfig,
    NetworkAccessConfig,
    PreferenceConfig,
    SandboxConfig,
    SkillsConfig,
)
from .parser import ConfigError, parse_section

logger = logging.getLogger(__name__)

# Re-export so callers can ``from tank_backend.config.app_config import ConfigError``
__all__ = ["AppConfig", "ConfigError"]


@dataclass(frozen=True)
class FeatureConfig:
    """Typed configuration for a plugin feature slot (asr, tts, speaker)."""

    plugin: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = False
    extension: str | None = None


@dataclass(frozen=True)
class AppConfig:
    """Strongly-typed, immutable application configuration.

    Created once at startup via ``load()`` or ``from_raw_dict()``.
    Every field is a frozen dataclass — no raw dicts leak to consumers.
    """

    # LLM profiles (keyed by name)
    llm_profiles: dict[str, LLMProfile] = field(default_factory=dict)

    # Pipeline
    brain: BrainConfig = field(default_factory=BrainConfig)
    echo_guard: EchoGuardConfig = field(default_factory=EchoGuardConfig)
    assistant: AssistantConfig = field(default_factory=AssistantConfig)

    # Context & memory
    context: ContextConfig = field(default_factory=ContextConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    preferences: PreferenceConfig = field(default_factory=PreferenceConfig)

    # Tools & policies
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    network_access: NetworkAccessConfig = field(default_factory=NetworkAccessConfig)
    file_access: FileAccessConfig = field(default_factory=FileAccessConfig)
    command_security: CommandSecurityConfig = field(default_factory=CommandSecurityConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)

    # Agent orchestration
    agents: AgentsConfig = field(default_factory=AgentsConfig)

    # Skills
    skills: SkillsConfig = field(default_factory=SkillsConfig)

    # Jobs
    jobs: JobsConfig = field(default_factory=JobsConfig)

    # Observability
    alerting: AlertingConfig = field(default_factory=AlertingConfig)
    health_monitor: HealthMonitorConfig = field(default_factory=HealthMonitorConfig)

    # Plugin features
    asr: FeatureConfig = field(default_factory=FeatureConfig)
    tts: FeatureConfig = field(default_factory=FeatureConfig)
    speaker: FeatureConfig = field(default_factory=FeatureConfig)

    # Raw config dict — kept for backward-compat ``get_section()``
    _raw: dict[str, Any] = field(default_factory=dict, repr=False, compare=False)

    # ── Factories ─────────────────────────────────────────────────

    @classmethod
    def load(cls, config_path: Path | str, registry: object | None = None) -> AppConfig:
        """Load from a YAML file with env-var interpolation."""
        from ..plugin.yaml_loader import load_yaml

        raw = load_yaml(config_path)
        logger.info("Loaded config from %s", config_path)
        cfg = cls.from_raw_dict(raw)
        if registry is not None:
            cls._validate_features(cfg, registry)
        return cfg

    @classmethod
    def from_raw_dict(cls, raw: dict[str, Any]) -> AppConfig:
        """Parse all sections from an already-loaded dict.

        Raises ``ConfigError`` on any validation failure.
        """
        try:
            llm_profiles = _parse_llm_profiles(raw.get("llm", {}))

            return cls(
                llm_profiles=llm_profiles,
                brain=parse_section(BrainConfig, raw.get("brain")),
                echo_guard=parse_section(EchoGuardConfig, raw.get("echo_guard")),
                assistant=parse_section(AssistantConfig, raw.get("assistant")),
                context=parse_section(ContextConfig, raw.get("context")),
                memory=parse_section(MemoryConfig, raw.get("memory")),
                preferences=parse_section(PreferenceConfig, raw.get("preferences")),
                sandbox=parse_section(SandboxConfig, raw.get("sandbox")),
                network_access=parse_section(NetworkAccessConfig, raw.get("network_access")),
                file_access=parse_section(FileAccessConfig, raw.get("file_access")),
                command_security=parse_section(CommandSecurityConfig, raw.get("command_security")),
                audit=parse_section(AuditConfig, raw.get("audit")),
                agents=parse_section(AgentsConfig, raw.get("agents")),
                skills=parse_section(SkillsConfig, raw.get("skills")),
                jobs=parse_section(JobsConfig, raw.get("jobs")),
                alerting=parse_section(AlertingConfig, raw.get("alerting")),
                health_monitor=parse_section(HealthMonitorConfig, raw.get("health_monitor")),
                asr=_parse_feature(raw, "asr"),
                tts=_parse_feature(raw, "tts"),
                speaker=_parse_feature(raw, "speaker"),
                _raw=raw,
            )
        except ConfigError:
            raise
        except (TypeError, ValueError, KeyError) as exc:
            raise ConfigError(f"Invalid configuration: {exc}") from exc

    # ── Public accessors ──────────────────────────────────────────

    def get_llm_profile(self, name: str = "default") -> LLMProfile:
        """Return a named LLM profile.

        Raises ``ConfigError`` if the profile doesn't exist.
        """
        if name not in self.llm_profiles:
            available = list(self.llm_profiles.keys())
            raise ConfigError(
                f"LLM profile '{name}' not found. Available: {available}"
            )
        return self.llm_profiles[name]

    def list_llm_profiles(self) -> list[str]:
        return list(self.llm_profiles.keys())

    def is_feature_enabled(self, name: str) -> bool:
        feat = getattr(self, name, None)
        if isinstance(feat, FeatureConfig):
            return feat.enabled
        return False

    def get_capabilities(self) -> dict[str, bool]:
        return {
            "asr": self.asr.enabled,
            "tts": self.tts.enabled,
            "speaker_id": self.speaker.enabled,
        }

    # ── Backward compatibility ────────────────────────────────────

    def get_section(self, name: str, defaults: dict[str, Any] | None = None) -> dict[str, Any]:
        """Return a raw config section (for incremental migration)."""
        section = self._raw.get(name, {})
        if defaults:
            return {**defaults, **section}
        return dict(section) if section else {}

    def get_feature_config(self, name: str) -> FeatureConfig:
        """Backward-compat: return FeatureConfig for a plugin slot."""
        return getattr(self, name, FeatureConfig())

    # ── Private ───────────────────────────────────────────────────

    @staticmethod
    def _validate_features(cfg: AppConfig, registry: object) -> None:
        from ..plugin.manager import validate_feature_refs

        # Build a thin adapter that the existing validator expects
        validate_feature_refs(cfg, registry)  # type: ignore[arg-type]


def _parse_llm_profiles(llm_raw: dict[str, Any]) -> dict[str, LLMProfile]:
    if not llm_raw:
        return {}

    profiles = {}
    for name, profile_raw in llm_raw.items():
        if not isinstance(profile_raw, dict):
            continue
        try:
            profiles[name] = resolve_profile(name, profile_raw)
        except ValueError:
            logger.warning("Skipping invalid LLM profile '%s'", name)

    return profiles


def _parse_feature(raw: dict[str, Any], name: str) -> FeatureConfig:
    feature_data = raw.get(name, {})
    if not feature_data:
        return FeatureConfig(enabled=False)

    if not feature_data.get("enabled", True):
        return FeatureConfig(enabled=False)

    extension_ref = feature_data.get("extension")
    plugin_name = feature_data.get("plugin", "")
    if extension_ref and not plugin_name:
        plugin_name = extension_ref.split(":")[0]

    if not plugin_name:
        return FeatureConfig(enabled=False)

    return FeatureConfig(
        plugin=plugin_name,
        config=feature_data.get("config", {}),
        enabled=True,
        extension=extension_ref,
    )
