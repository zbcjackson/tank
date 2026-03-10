"""Extension registry — loaded extension instances keyed by (plugin, ext)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class ExtensionRegistry:
    """Loaded extension instances, keyed by ``(plugin_name, extension_name)``."""

    def __init__(self) -> None:
        self._instances: dict[tuple[str, str], object] = {}

    def register(
        self, plugin_name: str, ext_name: str, instance: object
    ) -> None:
        key = (plugin_name, ext_name)
        if key in self._instances:
            logger.warning("Overwriting extension %s:%s", plugin_name, ext_name)
        self._instances[key] = instance

    def get(self, plugin_name: str, ext_name: str) -> object | None:
        return self._instances.get((plugin_name, ext_name))

    def get_all_by_type(self, ext_type: str) -> list[object]:
        """Return all instances whose extension name matches *ext_type*."""
        return [
            inst
            for (_, ename), inst in self._instances.items()
            if ename == ext_type
        ]

    def __len__(self) -> int:
        return len(self._instances)
