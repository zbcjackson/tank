"""Plugin manifest reading from pyproject.toml [tool.tank] section."""

from __future__ import annotations

import importlib.metadata
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtensionManifest:
    """Describes a single extension provided by a plugin."""

    name: str  # e.g. "tts"
    type: str  # e.g. "tts" | "asr" | "speaker_id" | "tool"
    factory: str  # e.g. "tts_edge:create_engine"


@dataclass(frozen=True)
class PluginManifest:
    """Describes a plugin and the extensions it provides."""

    plugin_name: str
    display_name: str
    description: str
    extensions: list[ExtensionManifest] = field(default_factory=list)


def read_plugin_manifest(
    plugin_name: str,
    *,
    slot_type: str | None = None,
) -> PluginManifest:
    """Read ``[tool.tank]`` from an installed package's pyproject.toml.

    Falls back to a synthetic single-extension manifest for legacy plugins
    that expose ``create_engine()`` but have no ``[tool.tank]`` section.

    Args:
        plugin_name: Package name (e.g. ``"tts-edge"``).
        slot_type: Slot type hint used for legacy fallback (e.g. ``"tts"``).

    Returns:
        PluginManifest describing the plugin and its extensions.

    Raises:
        ImportError: If the package is not installed.
    """
    try:
        dist = importlib.metadata.distribution(plugin_name)
    except importlib.metadata.PackageNotFoundError as exc:
        raise ImportError(
            f"Plugin '{plugin_name}' is not installed."
        ) from exc

    # Try to read [tool.tank] from the package's pyproject.toml
    tank_meta = _read_tool_tank(dist)

    if tank_meta is not None:
        return _parse_manifest(plugin_name, tank_meta)

    # Legacy fallback: synthesize manifest from create_engine convention
    logger.debug(
        "No [tool.tank] in '%s'; using legacy fallback", plugin_name
    )
    return _legacy_manifest(plugin_name, slot_type)


def _read_tool_tank(
    dist: importlib.metadata.Distribution,
) -> dict | None:
    """Extract ``[tool.tank]`` dict from a distribution's pyproject.toml."""
    # importlib.metadata doesn't expose pyproject.toml directly on all
    # Python versions, so we try to read it from the package's source.
    try:
        import tomllib
    except ModuleNotFoundError:  # Python < 3.11
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ModuleNotFoundError:
            logger.debug("tomllib/tomli unavailable; skipping manifest read")
            return None

    # Locate pyproject.toml via the distribution's origin
    files = dist.files
    if files:
        # Find the package root from the first file in the distribution
        for f in files:
            located = dist.locate_file(f)
            if located is not None:
                pkg_root = Path(located).resolve().parent
                # Walk up to find pyproject.toml
                for parent in (pkg_root, *pkg_root.parents):
                    candidate = parent / "pyproject.toml"
                    if candidate.exists():
                        with open(candidate, "rb") as fh:
                            data = tomllib.load(fh)
                        return data.get("tool", {}).get("tank")
                break

    return None


def _parse_manifest(plugin_name: str, tank_meta: dict) -> PluginManifest:
    """Parse a ``[tool.tank]`` dict into a PluginManifest."""
    extensions = []
    for ext_raw in tank_meta.get("extensions", []):
        extensions.append(
            ExtensionManifest(
                name=ext_raw["name"],
                type=ext_raw["type"],
                factory=ext_raw["factory"],
            )
        )

    return PluginManifest(
        plugin_name=tank_meta.get("plugin_name", plugin_name),
        display_name=tank_meta.get("display_name", plugin_name),
        description=tank_meta.get("description", ""),
        extensions=extensions,
    )


def _legacy_manifest(
    plugin_name: str,
    slot_type: str | None = None,
) -> PluginManifest:
    """Build a synthetic manifest for plugins without ``[tool.tank]``."""
    module_name = plugin_name.replace("-", "_")
    ext_type = slot_type or _infer_type_from_name(plugin_name)
    ext_name = ext_type  # legacy: extension name == type

    return PluginManifest(
        plugin_name=plugin_name,
        display_name=plugin_name,
        description=f"Legacy plugin: {plugin_name}",
        extensions=[
            ExtensionManifest(
                name=ext_name,
                type=ext_type,
                factory=f"{module_name}:create_engine",
            )
        ],
    )


def _infer_type_from_name(plugin_name: str) -> str:
    """Best-effort type inference from plugin name prefix."""
    lower = plugin_name.lower()
    if lower.startswith("tts"):
        return "tts"
    if lower.startswith("asr"):
        return "asr"
    if lower.startswith("speaker"):
        return "speaker_id"
    return "unknown"
