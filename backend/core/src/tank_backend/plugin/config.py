"""Plugin configuration loader."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SlotConfig:
    """Typed configuration for a single plugin slot."""

    plugin: str
    config: dict[str, Any] = field(default_factory=dict)


class PluginConfig:
    """Plugin configuration loaded from plugins.yaml."""

    def __init__(self, config_path: Path | str = "plugins/plugins.yaml"):
        self._config_path = Path(config_path)
        self._config: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load configuration from YAML file."""
        try:
            with open(self._config_path) as f:
                self._config = yaml.safe_load(f) or {}
            logger.info(f"Loaded plugin config from {self._config_path}")
        except FileNotFoundError:
            logger.warning(f"Plugin config not found: {self._config_path}")
        except Exception as e:
            logger.error(f"Failed to load plugin config: {e}")
            raise

    def get_slot_config(self, slot: str) -> SlotConfig:
        """
        Get configuration for a plugin slot.

        Args:
            slot: Plugin slot name (e.g., "tts", "asr", "llm")

        Returns:
            SlotConfig with plugin name and config dict.
        """
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
