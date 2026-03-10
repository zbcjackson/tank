"""Plugin system for Tank backend."""

from .config import AppConfig, PluginConfig, SlotConfig, find_config_yaml
from .manager import ConfigError, PluginManager
from .manifest import ExtensionManifest, PluginManifest, read_plugin_manifest
from .registry import ExtensionRegistry

__all__ = [
    "AppConfig",
    "ConfigError",
    "ExtensionManifest",
    "ExtensionRegistry",
    "PluginConfig",
    "PluginManager",
    "PluginManifest",
    "SlotConfig",
    "find_config_yaml",
    "read_plugin_manifest",
]
