"""Application configuration loader (YAML-based)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..llm.profile import LLMProfile, resolve_profile
from .yaml_loader import load_yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SlotConfig:
    """Typed configuration for a single plugin slot."""

    plugin: str
    config: dict[str, Any] = field(default_factory=dict)


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

    def __init__(self, config_path: Path | str | None = None):
        if config_path is None:
            config_path = find_config_yaml()
        self._config_path = Path(config_path)
        self._config: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load configuration from YAML file with ${VAR} interpolation."""
        try:
            self._config = load_yaml(self._config_path)
            if self._config:
                logger.info(f"Loaded config from {self._config_path}")
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            raise

    def get_slot_config(self, slot: str) -> SlotConfig:
        """Get configuration for a plugin slot (e.g. "tts")."""
        slot_config = self._config.get(slot, {})
        if not slot_config:
            raise ValueError(f"No configuration found for slot '{slot}'")

        plugin_name = slot_config.get("plugin")
        if not plugin_name:
            raise ValueError(f"No plugin specified for slot '{slot}'")

        return SlotConfig(
            plugin=plugin_name,
            config=slot_config.get("config", {}),
        )

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


# Backward-compatible alias
PluginConfig = AppConfig
