"""Plugin system for Tank backend."""

from .config import AppConfig, PluginConfig, SlotConfig, find_config_yaml
from .loader import load_plugin

__all__ = ["AppConfig", "PluginConfig", "SlotConfig", "find_config_yaml", "load_plugin"]
