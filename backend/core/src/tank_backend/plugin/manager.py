"""Plugin lifecycle manager — discovery, loading, registration, validation."""

from __future__ import annotations

import importlib.metadata
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .manifest import (
    PluginManifest,
    _parse_manifest,
    _read_tool_tank,
    read_plugin_manifest,
)
from .registry import ExtensionRegistry

logger = logging.getLogger(__name__)

# Maps config.yaml slot names to extension types declared in manifests.
SLOT_TYPE_MAP: dict[str, str] = {
    "asr": "asr",
    "tts": "tts",
    "speaker": "speaker_id",
}


class ConfigError(Exception):
    """Raised when config.yaml has invalid extension references."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__(
            "Config validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
        )


@dataclass
class ExtensionEntry:
    """Per-extension enable/disable in plugins.yaml."""

    name: str
    enabled: bool = True


@dataclass
class PluginEntry:
    """Per-plugin entry in plugins.yaml."""

    name: str
    enabled: bool = True
    extensions: dict[str, ExtensionEntry] = field(default_factory=dict)


class PluginManager:
    """Lifecycle orchestrator: discovery → loading → registration → validation.

    Reads ``plugins.yaml`` to know which plugins/extensions are enabled,
    reads each plugin's ``[tool.tank]`` manifest, and populates an
    :class:`ExtensionRegistry` with the enabled extensions.
    """

    def __init__(self, plugins_yaml_path: Path | None = None) -> None:
        self._plugins_yaml_path = plugins_yaml_path
        self._registry = ExtensionRegistry()
        self._entries: dict[str, PluginEntry] = {}

    @property
    def registry(self) -> ExtensionRegistry:
        return self._registry

    # ── Discovery ──────────────────────────────────────────────

    def discover_plugins(self) -> dict[str, PluginManifest]:
        """Scan installed distributions for ``[tool.tank]`` manifests."""
        found: dict[str, PluginManifest] = {}
        for dist in importlib.metadata.distributions():
            tank_meta = _read_tool_tank(dist)
            if tank_meta is None:
                continue
            manifest = _parse_manifest(dist.metadata["Name"], tank_meta)
            found[manifest.plugin_name] = manifest
            logger.debug("Discovered plugin: %s", manifest.plugin_name)
        return found

    def generate_plugins_yaml(self) -> Path:
        """Discover plugins and write ``plugins.yaml`` (all enabled).

        Returns the path to the generated file.
        """
        plugins = self.discover_plugins()
        path = self._resolve_plugins_yaml_path()

        data: dict[str, Any] = {}
        for name, manifest in sorted(plugins.items()):
            ext_entries: dict[str, Any] = {}
            for ext in manifest.extensions:
                ext_entries[ext.name] = {"enabled": True}
            data[name] = {
                "enabled": True,
                "extensions": ext_entries,
            }

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=True))
        logger.info("Generated %s with %d plugin(s)", path, len(data))
        return path

    # ── Loading ────────────────────────────────────────────────

    def load_all(self) -> ExtensionRegistry:
        """Main entry point. Read plugins.yaml, register enabled extensions.

        If ``plugins.yaml`` does not exist, auto-generates it via discovery.
        """
        path = self._resolve_plugins_yaml_path()

        if not path.exists():
            logger.info("plugins.yaml not found — running auto-discovery")
            self.generate_plugins_yaml()

        self._entries = self._read_plugins_yaml(path)

        for plugin_name, entry in self._entries.items():
            if not entry.enabled:
                logger.debug("Plugin %s is disabled, skipping", plugin_name)
                continue
            self._register_plugin(plugin_name, entry)

        logger.info(
            "Loaded %d extension(s) from %d plugin(s)",
            len(self._registry),
            len(self._entries),
        )
        return self._registry

    # ── Lifecycle helpers ──────────────────────────────────────

    def install(self, plugin_name: str) -> None:
        """Add a plugin to plugins.yaml with all extensions enabled."""
        manifest = read_plugin_manifest(plugin_name)
        entry = PluginEntry(
            name=plugin_name,
            extensions={
                ext.name: ExtensionEntry(name=ext.name, enabled=True)
                for ext in manifest.extensions
            },
        )
        self._entries[plugin_name] = entry
        self._write_plugins_yaml()

        # Register immediately
        self._register_plugin(plugin_name, entry)

    def uninstall(self, plugin_name: str) -> None:
        """Remove a plugin from plugins.yaml and unregister its extensions."""
        entry = self._entries.pop(plugin_name, None)
        if entry is None:
            return
        for ext_name in entry.extensions:
            self._registry.unregister(f"{plugin_name}:{ext_name}")
        self._write_plugins_yaml()

    def enable_plugin(self, plugin_name: str) -> None:
        """Enable a plugin and register its extensions."""
        entry = self._entries.get(plugin_name)
        if entry is None:
            return
        entry.enabled = True
        self._register_plugin(plugin_name, entry)
        self._write_plugins_yaml()

    def disable_plugin(self, plugin_name: str) -> None:
        """Disable a plugin and unregister its extensions."""
        entry = self._entries.get(plugin_name)
        if entry is None:
            return
        entry.enabled = False
        for ext_name in entry.extensions:
            self._registry.unregister(f"{plugin_name}:{ext_name}")
        self._write_plugins_yaml()

    def enable_extension(self, plugin_name: str, ext_name: str) -> None:
        """Enable a single extension within a plugin."""
        entry = self._entries.get(plugin_name)
        if entry is None or ext_name not in entry.extensions:
            return
        entry.extensions[ext_name].enabled = True
        # Re-register the whole plugin to pick up the change
        self._register_plugin(plugin_name, entry)
        self._write_plugins_yaml()

    def disable_extension(self, plugin_name: str, ext_name: str) -> None:
        """Disable a single extension within a plugin."""
        entry = self._entries.get(plugin_name)
        if entry is None or ext_name not in entry.extensions:
            return
        entry.extensions[ext_name].enabled = False
        self._registry.unregister(f"{plugin_name}:{ext_name}")
        self._write_plugins_yaml()

    # ── Validation ─────────────────────────────────────────────

    def validate_config(self, app_config: object) -> None:
        """Validate config.yaml extension refs against the registry.

        Checks:
          1. Referenced extension exists in registry.
          2. Extension type matches the slot's expected type.

        Raises:
            ConfigError: Listing all violations found.
        """
        errors: list[str] = []
        for slot_name, expected_type in SLOT_TYPE_MAP.items():
            slot_cfg = app_config.get_slot_config(slot_name)  # type: ignore[attr-defined]
            if not slot_cfg.enabled or not slot_cfg.extension:
                continue

            if not self._registry.has(slot_cfg.extension):
                errors.append(
                    f"Slot '{slot_name}': extension '{slot_cfg.extension}' "
                    f"is not registered (not installed or disabled)"
                )
                continue

            ext_manifest = self._registry.get(slot_cfg.extension)
            if ext_manifest is not None and ext_manifest.type != expected_type:
                errors.append(
                    f"Slot '{slot_name}': extension '{slot_cfg.extension}' "
                    f"has type '{ext_manifest.type}', expected '{expected_type}'"
                )

        if errors:
            raise ConfigError(errors)

    # ── Internal ───────────────────────────────────────────────

    def _resolve_plugins_yaml_path(self) -> Path:
        """Return the path to plugins.yaml, next to config.yaml."""
        if self._plugins_yaml_path is not None:
            return self._plugins_yaml_path

        from .config import find_config_yaml

        config_yaml = find_config_yaml()
        return config_yaml.parent / "plugins.yaml"

    def _read_plugins_yaml(self, path: Path) -> dict[str, PluginEntry]:
        """Parse plugins.yaml into PluginEntry objects."""
        try:
            raw = yaml.safe_load(path.read_text()) or {}
        except FileNotFoundError:
            return {}

        entries: dict[str, PluginEntry] = {}
        for plugin_name, plugin_data in raw.items():
            if not isinstance(plugin_data, dict):
                continue
            ext_entries: dict[str, ExtensionEntry] = {}
            for ext_name, ext_data in plugin_data.get("extensions", {}).items():
                ext_enabled = ext_data.get("enabled", True) if isinstance(ext_data, dict) else True
                ext_entries[ext_name] = ExtensionEntry(name=ext_name, enabled=ext_enabled)

            entries[plugin_name] = PluginEntry(
                name=plugin_name,
                enabled=plugin_data.get("enabled", True),
                extensions=ext_entries,
            )
        return entries

    def _register_plugin(self, plugin_name: str, entry: PluginEntry) -> None:
        """Read manifest and register enabled extensions."""
        try:
            manifest = read_plugin_manifest(plugin_name)
        except ImportError:
            logger.warning(
                "Plugin '%s' listed in plugins.yaml but not installed", plugin_name
            )
            return

        for ext in manifest.extensions:
            ext_entry = entry.extensions.get(ext.name)
            if ext_entry is not None and not ext_entry.enabled:
                logger.debug(
                    "Extension %s:%s is disabled, skipping", plugin_name, ext.name
                )
                continue
            self._registry.register(plugin_name, ext)

    def _write_plugins_yaml(self) -> None:
        """Persist current entries back to plugins.yaml."""
        path = self._resolve_plugins_yaml_path()
        data: dict[str, Any] = {}
        for name, entry in sorted(self._entries.items()):
            ext_data: dict[str, Any] = {}
            for ext_name, ext_entry in entry.extensions.items():
                ext_data[ext_name] = {"enabled": ext_entry.enabled}
            data[name] = {
                "enabled": entry.enabled,
                "extensions": ext_data,
            }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(data, default_flow_style=False, sort_keys=True))
