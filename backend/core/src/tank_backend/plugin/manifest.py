"""Plugin manifest reading from plugin.yaml files."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

MANIFEST_FILENAME = "plugin.yaml"
TASK_RUNTIME_API_VERSION = 1


@dataclass(frozen=True)
class ExtensionManifest:
    """Describes a single extension provided by a plugin."""

    name: str  # e.g. "tts"
    type: str  # e.g. "tts" | "asr" | "speaker_id" | "tool" | "subagent"
    factory: str  # e.g. "tts_edge:create_engine"
    permissions: tuple[str, ...] = ()
    runtime_api: int | None = None

    def __post_init__(self) -> None:
        if self.runtime_api is not None and (
            type(self.runtime_api) is not int or self.runtime_api < 1
            or self.type != "subagent"
        ):
            raise ValueError("runtime API must be a positive integer on a subagent extension")

    def check_runtime_api(self) -> None:
        """Version compatibility only; transport compliance is validated separately."""
        if self.runtime_api not in (None, TASK_RUNTIME_API_VERSION):
            raise ValueError(f"unsupported task runtime API: {self.runtime_api}")


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
            permissions=_parse_permissions(ext.get("permissions", [])),
            runtime_api=ext.get("runtime_api"),
        )
        for ext in data.get("extensions", [])
    ]

    names = [ext.name for ext in extensions]
    if len(set(names)) != len(names):
        raise ValueError(f"Duplicate extension names in {path}")

    return PluginManifest(
        plugin_name=data["name"],
        display_name=data.get("display_name", data["name"]),
        description=data.get("description", ""),
        extensions=extensions,
    )


def _parse_permissions(raw: object) -> tuple[str, ...]:
    allowed = {"desktop", "shell", "filesystem", "network"}
    if not isinstance(raw, list) or any(not isinstance(p, str) or p not in allowed for p in raw):
        raise ValueError("permissions must be a list of desktop/shell/filesystem/network")
    if len(set(raw)) != len(raw):
        raise ValueError("duplicate permissions")
    return tuple(raw)


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
    from ..config.app_config import find_config_yaml

    config_yaml = find_config_yaml()
    return config_yaml.parent.parent / "plugins"
