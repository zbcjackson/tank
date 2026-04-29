"""Config parsing utilities."""

from __future__ import annotations

import dataclasses
from typing import Any, TypeVar, get_type_hints

T = TypeVar("T")


class ConfigError(Exception):
    """Raised when configuration is invalid."""


def parse_section(cls: type[T], raw: dict[str, Any] | None) -> T:
    """Parse a raw YAML dict into a frozen dataclass.

    - ``None`` or empty dict → all defaults
    - Unknown keys are silently ignored (forward-compatible)
    - Type mismatches raise ``ConfigError``
    - Supports ``__config_flatten__`` for hoisting nested sub-dicts
    """
    if not raw:
        return cls()

    # Flatten nested dicts if the class declares __config_flatten__
    flatten_map = getattr(cls, "__config_flatten__", None)
    if flatten_map:
        raw = dict(raw)  # shallow copy to avoid mutating caller's dict
        for nested_key in flatten_map:
            nested = raw.pop(nested_key, None)
            if isinstance(nested, dict):
                raw.update(nested)

    fields = {f.name: f for f in dataclasses.fields(cls)}  # type: ignore[arg-type]
    filtered: dict[str, Any] = {}

    hints = get_type_hints(cls, include_extras=False)

    for key, value in raw.items():
        if key not in fields:
            continue

        expected = hints.get(key)
        if expected is not None and value is not None and not _check_type(value, expected):
            raise ConfigError(
                f"{cls.__name__}.{key}: expected {expected}, "
                f"got {type(value).__name__} ({value!r})"
            )

        filtered[key] = value

    try:
        return cls(**filtered)
    except TypeError as exc:
        raise ConfigError(f"{cls.__name__}: {exc}") from exc


def _check_type(value: Any, expected: Any) -> bool:
    """Lightweight type check for common config types."""
    origin = getattr(expected, "__origin__", None)

    # list[...], dict[...] — just check the container type
    if origin is list:
        return isinstance(value, list)
    if origin is dict:
        return isinstance(value, dict)

    # str | None, int | None, etc. (Union types)
    args = getattr(expected, "__args__", None)
    if args is not None and origin is not None:
        return any(_check_type(value, a) for a in args)

    # Plain types
    if expected is float:
        return isinstance(value, (int, float))
    if isinstance(expected, type):
        return isinstance(value, expected)

    return True
