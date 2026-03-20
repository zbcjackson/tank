"""YAML file loading with ${VAR} environment variable interpolation."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def load_yaml(path: Path | str) -> dict[str, Any]:
    """Load a YAML file with ``${VAR}`` environment variable interpolation.

    Args:
        path: Path to the YAML file.

    Returns:
        Parsed dict (empty dict if file not found).

    Raises:
        ValueError: If a ``${VAR}`` references an unset env var.
    """
    path = Path(path)
    try:
        raw_yaml = path.read_text()
    except FileNotFoundError:
        logger.warning(f"Config not found: {path}")
        return {}

    interpolated = _interpolate_env_vars(raw_yaml, path)
    return yaml.safe_load(interpolated) or {}


_ENV_VAR_PATTERN = re.compile(r'\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}')


def _interpolate_env_vars(text: str, source_path: Path) -> str:
    """Replace ``${VAR}`` and ``${VAR:-default}`` patterns with values.

    ``${VAR}`` — required; raises if unset.
    ``${VAR:-default}`` — optional; uses *default* if unset.
    ``${VAR:-}`` — optional; uses empty string if unset.

    Skips YAML comment lines (starting with ``#``) to avoid false matches.

    Raises:
        ValueError: If a required env var (no ``:-``) is not set.
    """
    def replacer(match: re.Match) -> str:
        var_name = match.group(1)
        default = match.group(2)  # None when no :- syntax
        value = os.environ.get(var_name)
        if value is None:
            if default is not None:
                return default
            raise ValueError(
                f"Environment variable '{var_name}' referenced in "
                f"{source_path} is not set"
            )
        return value

    lines = []
    for line in text.splitlines(keepends=True):
        if line.lstrip().startswith("#"):
            lines.append(line)
        else:
            lines.append(_ENV_VAR_PATTERN.sub(replacer, line))
    return "".join(lines)
