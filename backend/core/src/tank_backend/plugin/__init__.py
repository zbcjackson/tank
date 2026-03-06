"""Plugin system for Tank backend."""

from .config import PluginConfig, SlotConfig
from .loader import load_plugin

__all__ = ["PluginConfig", "SlotConfig", "load_plugin"]
