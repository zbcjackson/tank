"""Application configuration loader (YAML-based).

This module now delegates to :mod:`tank_backend.config.app_config` for
strongly-typed, validated configuration.  The ``AppConfig`` class here
is kept for backward compatibility — it builds the new typed config
internally and exposes typed properties alongside the legacy
``get_section()`` accessor.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..config.app_config import AppConfig as _TypedAppConfig
from ..config.app_config import FeatureConfig
from ..config.models import (
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
from ..llm.profile import LLMProfile, resolve_profile
from .yaml_loader import load_yaml

logger = logging.getLogger(__name__)

# Re-export for callers that import FeatureConfig from here
SlotConfig = FeatureConfig


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


class AppConfig:
    """Application configuration loaded from core/config.yaml.

    Builds a strongly-typed ``_TypedAppConfig`` internally.  Consumers
    can access typed properties (``self.brain``, ``self.echo_guard``, etc.)
    or fall back to ``get_section()`` during incremental migration.
    """

    def __init__(
        self,
        config_path: Path | str | None = None,
        registry: object | None = None,
    ):
        if config_path is None:
            config_path = find_config_yaml()
        self._config_path = Path(config_path)
        self._config: dict[str, Any] = {}
        self._registry = registry
        self._load()

        # Build typed config from the raw dict
        self._typed = _TypedAppConfig.from_raw_dict(self._config)

        if registry is not None:
            self._validate_features()

    def _load(self) -> None:
        """Load configuration from YAML file with ${VAR} interpolation."""
        try:
            self._config = load_yaml(self._config_path)
            if self._config:
                logger.info(f"Loaded config from {self._config_path}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise

    # ── Typed config properties ────────────────────────────────────

    @property
    def brain(self) -> BrainConfig:
        return self._typed.brain

    @property
    def echo_guard(self) -> EchoGuardConfig:
        return self._typed.echo_guard

    @property
    def assistant_config(self) -> AssistantConfig:
        return self._typed.assistant

    @property
    def context(self) -> ContextConfig:
        return self._typed.context

    @property
    def memory(self) -> MemoryConfig:
        return self._typed.memory

    @property
    def preferences(self) -> PreferenceConfig:
        return self._typed.preferences

    @property
    def sandbox(self) -> SandboxConfig:
        return self._typed.sandbox

    @property
    def network_access(self) -> NetworkAccessConfig:
        return self._typed.network_access

    @property
    def file_access(self) -> FileAccessConfig:
        return self._typed.file_access

    @property
    def command_security(self) -> CommandSecurityConfig:
        return self._typed.command_security

    @property
    def audit(self) -> AuditConfig:
        return self._typed.audit

    @property
    def agents(self) -> AgentsConfig:
        return self._typed.agents

    @property
    def skills(self) -> SkillsConfig:
        return self._typed.skills

    @property
    def jobs(self) -> JobsConfig:
        return self._typed.jobs

    @property
    def alerting(self) -> AlertingConfig:
        return self._typed.alerting

    @property
    def health_monitor(self) -> HealthMonitorConfig:
        return self._typed.health_monitor

    @property
    def asr(self) -> FeatureConfig:
        return self._typed.asr

    @property
    def tts(self) -> FeatureConfig:
        return self._typed.tts

    @property
    def speaker(self) -> FeatureConfig:
        return self._typed.speaker

    # ── Generic section access (legacy — migrate callers away) ─────

    def get_section(self, name: str, defaults: dict[str, Any] | None = None) -> dict[str, Any]:
        """Get a raw config section by name, merged with optional defaults."""
        section = self._config.get(name, {})
        if defaults:
            return {**defaults, **section}
        return dict(section) if section else {}

    # ── Feature helpers ───────────────────────────────────────────

    def get_feature_config(self, name: str) -> FeatureConfig:
        """Get configuration for a feature (e.g. ``"tts"``)."""
        return self._typed.get_feature_config(name)

    # Backward-compatible alias
    get_slot_config = get_feature_config

    def is_feature_enabled(self, name: str) -> bool:
        """Check whether a feature is enabled."""
        return self._typed.is_feature_enabled(name)

    # Backward-compatible alias
    is_slot_enabled = is_feature_enabled

    def get_capabilities(self) -> dict[str, bool]:
        """Return a dict of feature capabilities for the frontend."""
        return self._typed.get_capabilities()

    # ── LLM profiles ──────────────────────────────────────────────

    def get_llm_profile(self, name: str = "default") -> LLMProfile:
        """Resolve and return a named LLM profile.

        Raises:
            ValueError: If the profile name doesn't exist or is invalid.
        """
        llm_section = self._config.get("llm", {})
        raw = llm_section.get(name)
        if raw is None:
            raise ValueError(
                f"LLM profile '{name}' not found in {self._config_path}"
            )
        return resolve_profile(name, raw)

    def list_llm_profiles(self) -> list[str]:
        """Return the names of all configured LLM profiles."""
        return list(self._config.get("llm", {}).keys())

    # ── Feature validation ──────────────────────────────────────────

    def _validate_features(self) -> None:
        """Validate extension refs in config against the registry."""
        from .manager import validate_feature_refs

        validate_feature_refs(self, self._registry)  # type: ignore[arg-type]


# Backward-compatible alias
PluginConfig = AppConfig
