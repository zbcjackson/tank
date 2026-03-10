"""Generic plugin loader."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def load_extension(
    plugin_name: str,
    extension_name: str,
    config: dict,
) -> object:
    """Load a single extension from a plugin using its manifest.

    The *extension_name* is looked up in the plugin's ``[tool.tank]``
    manifest.  If the manifest is missing (legacy plugin), the loader
    falls back to ``create_engine(config)``.

    Args:
        plugin_name: Package name (e.g. ``"tts-edge"``).
        extension_name: Extension name declared in the manifest (e.g. ``"tts"``).
        config: Extension-specific configuration dict.

    Returns:
        Extension instance.
    """
    from .manifest import read_plugin_manifest

    manifest = read_plugin_manifest(plugin_name)

    # Find the requested extension
    ext_manifest = None
    for ext in manifest.extensions:
        if ext.name == extension_name:
            ext_manifest = ext
            break

    if ext_manifest is None:
        # Fallback: if there's exactly one extension, use it
        if len(manifest.extensions) == 1:
            ext_manifest = manifest.extensions[0]
        else:
            raise ValueError(
                f"Extension '{extension_name}' not found in plugin '{plugin_name}'. "
                f"Available: {[e.name for e in manifest.extensions]}"
            )

    # Parse factory "module:callable"
    if ":" in ext_manifest.factory:
        module_path, callable_name = ext_manifest.factory.rsplit(":", 1)
    else:
        module_path = ext_manifest.factory
        callable_name = "create_engine"

    module = importlib.import_module(module_path)
    factory = getattr(module, callable_name)

    instance = factory(config)
    logger.info(
        "Loaded extension %s:%s via %s",
        plugin_name,
        extension_name,
        ext_manifest.factory,
    )
    return instance


def load_plugin(
    slot: str,
    plugin_name: str,
    config: dict,
    plugins_root: Path | str = "plugins",
) -> object:
    """Load a plugin for the given slot (legacy API).

    Prefer :func:`load_extension` for new code.  This wrapper exists for
    backward compatibility and delegates to the direct import path.

    Args:
        slot: Plugin slot name (e.g., "tts", "asr", "llm")
        plugin_name: Plugin folder name (e.g., "tts-edge")
        config: Plugin-specific configuration dict
        plugins_root: Root directory containing plugin folders

    Returns:
        Plugin instance created by calling the plugin's create_engine(config)
    """
    # Convert plugin folder name to Python module name
    # "tts-edge" → "tts_edge"
    module_name = plugin_name.replace("-", "_")

    try:
        module = importlib.import_module(module_name)
        logger.info(f"Loaded plugin module: {module_name}")
    except ImportError as e:
        logger.error(f"Failed to import plugin '{plugin_name}': {e}")
        raise ImportError(
            f"Plugin '{plugin_name}' not found. "
            f"Make sure it's installed in the workspace."
        ) from e

    if not hasattr(module, "create_engine"):
        raise AttributeError(
            f"Plugin '{plugin_name}' must export a create_engine(config) function"
        )

    create_engine = module.create_engine

    try:
        instance = create_engine(config)
        logger.info(f"Created {slot} plugin: {plugin_name}")
        return instance
    except Exception as e:
        logger.error(f"Failed to create plugin '{plugin_name}': {e}")
        raise
