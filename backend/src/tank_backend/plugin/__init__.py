"""Plugin system for Tank backend."""

from .config import PluginConfig
from .loader import load_plugin

__all__ = ["PluginConfig", "load_plugin"]
