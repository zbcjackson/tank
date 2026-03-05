"""Plugin configuration loader."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


class PluginConfig:
    """Plugin configuration loaded from plugins.yaml."""

    def __init__(self, config_path: Path | str = "plugins/plugins.yaml"):
        self._config_path = Path(config_path)
        self._config: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load configuration from YAML file."""
        if not self._config_path.exists():
            logger.warning(f"Plugin config not found: {self._config_path}")
            return

        try:
            with open(self._config_path) as f:
                self._config = yaml.safe_load(f) or {}
            logger.info(f"Loaded plugin config from {self._config_path}")
        except Exception as e:
            logger.error(f"Failed to load plugin config: {e}")
            raise

    def get_slot_config(self, slot: str) -> dict[str, Any]:
        """
        Get configuration for a plugin slot.

        Args:
            slot: Plugin slot name (e.g., "tts", "asr", "llm")

        Returns:
            Dict with keys:
                - plugin: Plugin name (folder name)
                - config: Plugin-specific config dict
        """
        slot_config = self._config.get(slot, {})
        if not slot_config:
            raise ValueError(f"No configuration found for slot '{slot}'")

        plugin_name = slot_config.get("plugin")
        if not plugin_name:
            raise ValueError(f"No plugin specified for slot '{slot}'")

        return {
            "plugin": plugin_name,
            "config": slot_config.get("config", {}),
        }
