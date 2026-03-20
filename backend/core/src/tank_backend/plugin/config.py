"""Application configuration loader (YAML-based)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..llm.profile import LLMProfile, resolve_profile
from .yaml_loader import load_yaml

logger = logging.getLogger(__name__)

# Sentinel for "no plugin" (disabled feature)
_DISABLED_PLUGIN = ""


@dataclass(frozen=True)
class FeatureConfig:
    """Typed configuration for a single feature (e.g. asr, tts, speaker).

    When ``enabled`` is False the feature is inactive — callers should skip
    loading the plugin entirely.

    ``extension`` holds the ``{plugin}:{ext}`` reference when using the
    new manifest-aware format.  For legacy configs that only specify
    ``plugin:``, it is ``None`` and the loader falls back to
    ``create_engine()``.
    """

    plugin: str = _DISABLED_PLUGIN
    config: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    extension: str | None = None


# Backward-compatible alias
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
    """Application configuration loaded from core/config.yaml."""

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

    # ── Generic section access ─────────────────────────────────────

    def get_section(self, name: str, defaults: dict[str, Any] | None = None) -> dict[str, Any]:
        """Get a raw config section by name, merged with optional defaults."""
        section = self._config.get(name, {})
        if defaults:
            return {**defaults, **section}
        return dict(section) if section else {}

    # ── Feature helpers ───────────────────────────────────────────

    def get_feature_config(self, name: str) -> FeatureConfig:
        """Get configuration for a feature (e.g. ``"tts"``).

        Returns a *disabled* ``FeatureConfig`` when the feature section is
        absent from the YAML or has ``enabled: false``.  This lets
        callers skip plugin loading without catching exceptions.
        """
        feature_data = self._config.get(name, {})
        if not feature_data:
            return FeatureConfig(enabled=False)

        # Explicit ``enabled: false`` in YAML
        if not feature_data.get("enabled", True):
            return FeatureConfig(enabled=False)

        # New format: ``extension: plugin:ext``
        extension_ref = feature_data.get("extension")

        # Legacy format: ``plugin: plugin-name``
        plugin_name = feature_data.get("plugin", "")

        # Derive plugin name from extension ref if present
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

    # Backward-compatible alias
    get_slot_config = get_feature_config

    def is_feature_enabled(self, name: str) -> bool:
        """Check whether a feature is enabled."""
        return self.get_feature_config(name).enabled

    # Backward-compatible alias
    is_slot_enabled = is_feature_enabled

    def get_capabilities(self) -> dict[str, bool]:
        """Return a dict of feature capabilities for the frontend."""
        return {
            "asr": self.is_feature_enabled("asr"),
            "tts": self.is_feature_enabled("tts"),
            "speaker_id": self.is_feature_enabled("speaker"),
        }

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
        """Validate extension refs in config against the registry.

        Raises:
            ConfigError: If any feature references an unregistered or
                type-mismatched extension.
        """
        from .manager import validate_feature_refs

        validate_feature_refs(self, self._registry)  # type: ignore[arg-type]


# Backward-compatible alias
PluginConfig = AppConfig
