"""Plugin system for Tank backend."""

from .config import AppConfig, PluginConfig, SlotConfig, find_config_yaml
from .loader import load_extension, load_plugin
from .manifest import ExtensionManifest, PluginManifest, read_plugin_manifest
from .registry import ExtensionRegistry

__all__ = [
    "AppConfig",
    "ExtensionManifest",
    "ExtensionRegistry",
    "PluginConfig",
    "PluginManifest",
    "SlotConfig",
    "find_config_yaml",
    "load_extension",
    "load_plugin",
    "read_plugin_manifest",
]
