"""Plugin system for Tank backend."""

from ..config import AppConfig, FeatureConfig, find_config_yaml
from .manager import ConfigError, PluginManager
from .manifest import (
    ExtensionManifest,
    PluginManifest,
    read_manifest_from_yaml,
    read_plugin_manifest,
)
from .registry import ExtensionRegistry

# Backward-compatible aliases
PluginConfig = AppConfig
SlotConfig = FeatureConfig

__all__ = [
    "AppConfig",
    "ConfigError",
    "ExtensionManifest",
    "ExtensionRegistry",
    "FeatureConfig",
    "PluginConfig",
    "PluginManager",
    "PluginManifest",
    "SlotConfig",
    "find_config_yaml",
    "read_manifest_from_yaml",
    "read_plugin_manifest",
]
