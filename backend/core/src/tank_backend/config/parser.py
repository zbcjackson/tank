"""Config parsing utilities."""

from __future__ import annotations

import dataclasses
import enum
from typing import Any, TypeVar, get_args, get_origin, get_type_hints

T = TypeVar("T")


class ConfigError(Exception):
    """Raised when configuration is invalid."""


def parse_section(cls: type[T], raw: dict[str, Any] | None) -> T:
    """Parse a raw YAML dict into a frozen dataclass.

    - ``None`` or empty dict → all defaults
    - Unknown keys are silently ignored (forward-compatible)
    - Type mismatches raise ``ConfigError``
    - Supports ``__config_flatten__`` for hoisting nested sub-dicts
    - Recursively parses nested dataclass fields and tuple[Dataclass, ...] from lists
    - Converts strings to Enum values when the field type is an Enum subclass
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
    hints = get_type_hints(cls, include_extras=False)
    filtered: dict[str, Any] = {}

    for key, value in raw.items():
        if key not in fields:
            continue

        expected = hints.get(key)
        if expected is not None and value is not None:
            converted = _convert_value(value, expected, cls.__name__, key)
            if converted is not _SENTINEL:
                filtered[key] = converted
                continue

            if not _check_type(value, expected):
                raise ConfigError(
                    f"{cls.__name__}.{key}: expected {expected}, "
                    f"got {type(value).__name__} ({value!r})"
                )

        filtered[key] = value

    try:
        return cls(**filtered)
    except TypeError as exc:
        raise ConfigError(f"{cls.__name__}: {exc}") from exc


_SENTINEL = object()


def _convert_value(value: Any, expected: Any, cls_name: str, key: str) -> Any:
    """Try to convert a raw YAML value to the expected type.

    Returns _SENTINEL if no conversion applies (caller should fall through).
    Handles:
    - Enum from string (e.g. AccessLevel from "allow")
    - tuple[Dataclass, ...] from list[dict]
    - tuple[str, ...] from list[str]
    - tuple[Enum, ...] from list[str]
    - Nested dataclass from dict
    """
    origin = get_origin(expected)
    args = get_args(expected)

    # Enum from string — convert "allow" → AccessLevel.ALLOW
    if isinstance(expected, type) and issubclass(expected, enum.Enum):
        if isinstance(value, expected):
            return value  # already an enum instance
        if isinstance(value, str):
            try:
                return expected(value)
            except ValueError:
                raise ConfigError(
                    f"{cls_name}.{key}: invalid value {value!r} for {expected.__name__}, "
                    f"valid values: {[e.value for e in expected]}"
                ) from None
        return _SENTINEL

    # tuple[SomeType, ...] — convert from list
    if origin is tuple and len(args) == 2 and args[1] is Ellipsis:
        item_type = args[0]
        if not isinstance(value, list):
            raise ConfigError(
                f"{cls_name}.{key}: expected list for tuple field, "
                f"got {type(value).__name__}"
            )
        if dataclasses.is_dataclass(item_type):
            return tuple(
                parse_section(item_type, item) if isinstance(item, dict) else item
                for item in value
            )
        # tuple[Enum, ...] from list[str]
        if isinstance(item_type, type) and issubclass(item_type, enum.Enum):
            return tuple(item_type(item) for item in value)
        # tuple[str, ...] or tuple[int, ...] — just convert list to tuple
        return tuple(value)

    # Nested dataclass from dict
    if dataclasses.is_dataclass(expected) and isinstance(expected, type):
        if isinstance(value, dict):
            return parse_section(expected, value)
        return _SENTINEL

    return _SENTINEL


def _check_type(value: Any, expected: Any) -> bool:
    """Lightweight type check for common config types."""
    origin = get_origin(expected)

    # Enum — accept string (will be converted by _convert_value on retry)
    if isinstance(expected, type) and issubclass(expected, enum.Enum):
        return isinstance(value, (str, expected))

    # tuple[...] — accept list (will be converted)
    if origin is tuple:
        return isinstance(value, (list, tuple))

    # list[...], dict[...] — just check the container type
    if origin is list:
        return isinstance(value, list)
    if origin is dict:
        return isinstance(value, dict)

    # str | None, int | None, etc. (Union types)
    args = get_args(expected)
    if args and origin is not None:
        return any(_check_type(value, a) for a in args)

    # Nested dataclass — accept dict
    if dataclasses.is_dataclass(expected) and isinstance(expected, type):
        return isinstance(value, dict)

    # Plain types
    if expected is float:
        return isinstance(value, (int, float))
    if isinstance(expected, type):
        return isinstance(value, expected)

    return True
