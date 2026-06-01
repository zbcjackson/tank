"""Strongly-typed, validated application configuration.

Replaces the old ``plugin.config.AppConfig`` which returned raw dicts.
All config.yaml sections are parsed into frozen dataclasses at startup.
If ``AppConfig.load()`` succeeds, the entire config is valid.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..llm.profile import LLMProfile, resolve_profile

if TYPE_CHECKING:
    from ..plugin.registry import ExtensionRegistry
from .models import (
    AgentsConfig,
    AlertingConfig,
    AssistantConfig,
    AuditConfig,
    BrainConfig,
    ChannelsConfig,
    CommandSecurityConfig,
    ConnectorInstanceConfig,
    ConnectorsConfig,
    ConsolidationConfig,
    ContextConfig,
    DatabaseConfig,
    EchoGuardConfig,
    FileAccessConfig,
    HealthMonitorConfig,
    JobsConfig,
    MemoryConfig,
    NetworkAccessConfig,
    NotificationHubConfig,
    PreferenceConfig,
    SandboxConfig,
    SkillsConfig,
)
from .parser import ConfigError, parse_section

logger = logging.getLogger(__name__)

# Re-export so callers can ``from tank_backend.config.app_config import ConfigError``
__all__ = ["AppConfig", "ConfigError", "find_config_yaml"]


def find_config_yaml() -> Path:
    """Locate ``core/config.yaml`` by walking up from this file and CWD.

    Search order:
      1. Ancestors of this source file (works inside the installed package).
      2. Ancestors of the current working directory (works for scripts).

    Raises:
        FileNotFoundError: If the file cannot be found.
    """
    roots = [Path(__file__).resolve(), Path.cwd().resolve()]
    for root in roots:
        for parent in (root, *root.parents):
            candidate = parent / "core" / "config.yaml"
            if candidate.exists():
                return candidate
    raise FileNotFoundError(
        "Could not find core/config.yaml. "
        "Make sure you're running from the project root or backend/ directory."
    )


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
    consolidation: ConsolidationConfig = field(default_factory=ConsolidationConfig)

    # Persistence
    database: DatabaseConfig = field(default_factory=DatabaseConfig)

    # Tools & policies
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)
    network_access: NetworkAccessConfig = field(default_factory=NetworkAccessConfig)
    file_access: FileAccessConfig = field(default_factory=FileAccessConfig)
    command_security: CommandSecurityConfig = field(default_factory=CommandSecurityConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)

    # Agent orchestration
    agents: AgentsConfig = field(default_factory=AgentsConfig)

    # Notifications
    notifications: NotificationHubConfig = field(default_factory=NotificationHubConfig)

    # Skills
    skills: SkillsConfig = field(default_factory=SkillsConfig)

    # Jobs
    jobs: JobsConfig = field(default_factory=JobsConfig)

    # Channels
    channels: ChannelsConfig = field(default_factory=ChannelsConfig)

    # Connectors (multi-instance — list of configured platform adapters)
    connectors: ConnectorsConfig = field(default_factory=ConnectorsConfig)

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
    def load(cls, config_path: Path | str, registry: ExtensionRegistry | None = None) -> AppConfig:
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
            if "default" not in llm_profiles:
                available = list(llm_profiles.keys())
                raise ConfigError(
                    f"LLM profile 'default' is required. Available: {available}"
                )

            return cls(
                llm_profiles=llm_profiles,
                brain=parse_section(BrainConfig, raw.get("brain")),
                echo_guard=parse_section(EchoGuardConfig, raw.get("echo_guard")),
                assistant=parse_section(AssistantConfig, raw.get("assistant")),
                context=parse_section(ContextConfig, raw.get("context")),
                memory=parse_section(MemoryConfig, raw.get("memory")),
                preferences=parse_section(PreferenceConfig, raw.get("preferences")),
                consolidation=parse_section(
                    ConsolidationConfig, raw.get("consolidation"),
                ),
                database=parse_section(DatabaseConfig, raw.get("database")),
                sandbox=parse_section(SandboxConfig, raw.get("sandbox")),
                network_access=parse_section(NetworkAccessConfig, raw.get("network_access")),
                file_access=parse_section(FileAccessConfig, raw.get("file_access")),
                command_security=parse_section(CommandSecurityConfig, raw.get("command_security")),
                audit=parse_section(AuditConfig, raw.get("audit")),
                agents=parse_section(AgentsConfig, raw.get("agents")),
                skills=parse_section(SkillsConfig, raw.get("skills")),
                jobs=parse_section(JobsConfig, raw.get("jobs")),
                channels=parse_section(ChannelsConfig, raw.get("channels")),
                connectors=_parse_connectors(raw.get("connectors")),
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
        """Return a named LLM profile, falling back to ``default``.

        ``from_raw_dict`` validates that ``default`` exists, so this method
        does not raise for AppConfigs constructed through that entry point.
        """
        profile = self.llm_profiles.get(name)
        if profile is not None:
            return profile
        if name != "default":
            logger.warning("LLM profile '%s' not found, falling back to 'default'", name)
        return self.llm_profiles["default"]

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
    def _validate_features(cfg: AppConfig, registry: ExtensionRegistry) -> None:
        from ..plugin.manager import validate_connector_refs, validate_feature_refs

        validate_feature_refs(cfg, registry)
        validate_connector_refs(cfg, registry)


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


def _parse_connectors(raw: Any) -> ConnectorsConfig:
    """Parse the ``connectors:`` top-level section.

    The section is a list of connector instance dicts. Each instance
    requires ``instance`` and ``extension`` string fields; ``config`` and
    ``enabled`` are optional. Duplicate ``instance`` names raise
    :class:`ConfigError`.
    """
    if not raw:
        return ConnectorsConfig()

    if not isinstance(raw, list):
        raise ConfigError(
            f"connectors: expected a list of instance dicts, got {type(raw).__name__}"
        )

    instances: list[ConnectorInstanceConfig] = []
    seen_names: set[str] = set()

    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ConfigError(
                f"connectors[{index}]: expected a dict, got {type(entry).__name__}"
            )

        instance_name = entry.get("instance", "")
        if not isinstance(instance_name, str) or not instance_name.strip():
            raise ConfigError(
                f"connectors[{index}]: 'instance' is required and must be a non-empty string"
            )

        extension_ref = entry.get("extension", "")
        if not isinstance(extension_ref, str) or not extension_ref.strip():
            raise ConfigError(
                f"connectors[{index}] '{instance_name}': 'extension' is required and "
                "must be a non-empty string"
            )

        if instance_name in seen_names:
            raise ConfigError(
                f"connectors: duplicate instance name '{instance_name}'"
            )
        seen_names.add(instance_name)

        cfg = entry.get("config", {}) or {}
        if not isinstance(cfg, dict):
            raise ConfigError(
                f"connectors[{index}] '{instance_name}': 'config' must be a mapping"
            )

        enabled = entry.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ConfigError(
                f"connectors[{index}] '{instance_name}': 'enabled' must be a bool"
            )

        instances.append(ConnectorInstanceConfig(
            instance=instance_name,
            extension=extension_ref,
            enabled=enabled,
            config=cfg,
        ))

    return ConnectorsConfig(instances=tuple(instances))
