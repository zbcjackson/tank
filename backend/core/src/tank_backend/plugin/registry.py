"""Extension registry — manifest catalog keyed by 'plugin:extension'."""

from __future__ import annotations

import importlib
import logging

from .manifest import ExtensionManifest

logger = logging.getLogger(__name__)


class ExtensionRegistry:
    """Extension manifests keyed by full name ``'plugin:extension'``.

    Stores *metadata* (``ExtensionManifest``), not live instances.
    Call :meth:`instantiate` to create an engine on demand.
    """

    def __init__(self) -> None:
        self._manifests: dict[str, ExtensionManifest] = {}

    # ── Registration ───────────────────────────────────────────

    def register(self, plugin_name: str, ext_manifest: ExtensionManifest) -> None:
        """Register an extension manifest under ``'plugin:ext'``."""
        full_name = f"{plugin_name}:{ext_manifest.name}"
        if full_name in self._manifests:
            logger.warning("Overwriting extension %s", full_name)
        self._manifests[full_name] = ext_manifest
        logger.debug("Registered extension %s (type=%s)", full_name, ext_manifest.type)

    def unregister(self, full_name: str) -> bool:
        """Remove an extension by full name. Returns True if it existed."""
        return self._manifests.pop(full_name, None) is not None

    # ── Lookup ─────────────────────────────────────────────────

    def get(self, full_name: str) -> ExtensionManifest | None:
        """Return the manifest for *full_name*, or ``None``."""
        return self._manifests.get(full_name)

    def has(self, full_name: str) -> bool:
        """Check whether *full_name* is registered."""
        return full_name in self._manifests

    def list_by_type(self, ext_type: str) -> list[tuple[str, ExtensionManifest]]:
        """Return all ``(full_name, manifest)`` pairs matching *ext_type*."""
        return [
            (name, m)
            for name, m in self._manifests.items()
            if m.type == ext_type
        ]

    def all_names(self) -> list[str]:
        """Return all registered full names."""
        return list(self._manifests.keys())

    # ── Instantiation ──────────────────────────────────────────

    def instantiate(self, full_name: str, config: dict) -> object:
        """Create an engine instance from the stored factory.

        The factory string is ``'module:callable'`` (e.g.
        ``'tts_edge:create_engine'``).  If no colon is present the
        callable defaults to ``create_engine``.

        Args:
            full_name: Registered extension key (e.g. ``'tts-edge:tts'``).
            config: Runtime configuration dict passed to the factory.

        Returns:
            The engine instance.

        Raises:
            KeyError: If *full_name* is not registered.
            ImportError: If the factory module cannot be imported.
            AttributeError: If the callable is not found in the module.
        """
        manifest = self._manifests.get(full_name)
        if manifest is None:
            raise KeyError(
                f"Extension '{full_name}' is not registered. "
                f"Available: {self.all_names()}"
            )

        # Parse "module:callable" with default
        module_path, _, callable_name = manifest.factory.rpartition(":")
        if not module_path:
            module_path = manifest.factory
            callable_name = "create_engine"

        module = importlib.import_module(module_path)
        factory = getattr(module, callable_name)

        instance = factory(config)
        logger.info("Instantiated %s via %s", full_name, manifest.factory)
        return instance

    def __len__(self) -> int:
        return len(self._manifests)
