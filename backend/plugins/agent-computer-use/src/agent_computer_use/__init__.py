"""Host-driven Computer Use plugin, explicitly selected through extension config."""

from .factory import create_subagent

__all__ = ["create_subagent"]
