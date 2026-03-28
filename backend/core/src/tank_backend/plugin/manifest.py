"""Plugin manifest reading from plugin.yaml files."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "plugin.yaml"


@dataclass(frozen=True)
class ExtensionManifest:
    """Describes a single extension provided by a plugin."""

    name: str  # e.g. "tts"
    type: str  # e.g. "tts" | "asr" | "speaker_id" | "tool"
    factory: str  # e.g. "tts_edge:create_engine"


@dataclass(frozen=True)
class PluginManifest:
    """Describes a plugin and the extensions it provides."""

    plugin_name: str
    display_name: str
    description: str
    extensions: list[ExtensionManifest] = field(default_factory=list)


def read_manifest_from_yaml(path: Path) -> PluginManifest:
    """Read plugin manifest from a ``plugin.yaml`` file.

    Args:
        path: Path to the ``plugin.yaml`` file.

    Returns:
        PluginManifest describing the plugin and its extensions.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If required fields are missing.
    """
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict) or "name" not in data:
        raise ValueError(f"Invalid plugin manifest: {path} (missing 'name')")

    extensions = [
        ExtensionManifest(
            name=ext["name"],
            type=ext["type"],
            factory=ext["factory"],
        )
        for ext in data.get("extensions", [])
    ]

    return PluginManifest(
        plugin_name=data["name"],
        display_name=data.get("display_name", data["name"]),
        description=data.get("description", ""),
        extensions=extensions,
    )


def read_plugin_manifest(
    plugin_name: str,
    *,
    plugins_dir: Path | None = None,
) -> PluginManifest:
    """Read manifest for a named plugin from the plugins directory.

    Locates ``plugins/<plugin_name>/plugin.yaml`` and parses it.

    Args:
        plugin_name: Plugin directory name (e.g. ``"tts-edge"``).
        plugins_dir: Root plugins directory. Auto-detected if ``None``.

    Returns:
        PluginManifest describing the plugin and its extensions.

    Raises:
        ImportError: If the plugin directory or manifest is not found.
    """
    if plugins_dir is None:
        plugins_dir = _find_plugins_dir()

    manifest_path = plugins_dir / plugin_name / MANIFEST_FILENAME
    if not manifest_path.exists():
        raise ImportError(
            f"Plugin '{plugin_name}' not found "
            f"(no {MANIFEST_FILENAME} at {manifest_path})"
        )

    return read_manifest_from_yaml(manifest_path)


def _find_plugins_dir() -> Path:
    """Locate the ``plugins/`` directory relative to ``config.yaml``.

    ``config.yaml`` lives at ``backend/core/config.yaml``;
    ``plugins/`` lives at ``backend/plugins/``.
    """
    from .config import find_config_yaml

    config_yaml = find_config_yaml()
    return config_yaml.parent.parent / "plugins"
