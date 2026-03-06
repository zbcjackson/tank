"""Generic plugin loader."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def load_plugin(
    slot: str,
    plugin_name: str,
    config: dict,
    plugins_root: Path | str = "plugins",
) -> object:
    """
    Load a plugin for the given slot.

    Args:
        slot: Plugin slot name (e.g., "tts", "asr", "llm")
        plugin_name: Plugin folder name (e.g., "tts-edge")
        config: Plugin-specific configuration dict
        plugins_root: Root directory containing plugin folders

    Returns:
        Plugin instance created by calling the plugin's create_engine(config)

    Raises:
        ImportError: If plugin module cannot be imported
        AttributeError: If plugin doesn't have create_engine function
        Exception: If plugin creation fails
    """
    # Convert plugin folder name to Python module name
    # "tts-edge" → "tts_edge"
    module_name = plugin_name.replace("-", "_")

    try:
        # Import the plugin module
        module = importlib.import_module(module_name)
        logger.info(f"Loaded plugin module: {module_name}")
    except ImportError as e:
        logger.error(f"Failed to import plugin '{plugin_name}': {e}")
        raise ImportError(
            f"Plugin '{plugin_name}' not found. "
            f"Make sure it's installed in the workspace."
        ) from e

    # Get the create_engine factory function
    if not hasattr(module, "create_engine"):
        raise AttributeError(
            f"Plugin '{plugin_name}' must export a create_engine(config) function"
        )

    create_engine = module.create_engine

    # Create and return the plugin instance
    try:
        instance = create_engine(config)
        logger.info(f"Created {slot} plugin: {plugin_name}")
        return instance
    except Exception as e:
        logger.error(f"Failed to create plugin '{plugin_name}': {e}")
        raise
