"""File access policy — evaluate allow/require_approval/deny per path and operation."""

from __future__ import annotations

import fnmatch
import logging
import os
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

AccessLevel = Literal["allow", "require_approval", "deny"]


@dataclass(frozen=True)
class FileAccessRule:
    """A single file access rule matching a set of path patterns."""

    paths: tuple[str, ...]
    read: AccessLevel = "allow"
    write: AccessLevel = "allow"
    delete: AccessLevel = "allow"
    reason: str = ""


@dataclass(frozen=True)
class AccessDecision:
    """Result of evaluating a file access policy."""

    level: AccessLevel
    reason: str


class FileAccessPolicy:
    """Evaluates file access rules. Backend-agnostic.

    Rules are evaluated top-down; first match wins.
    If no rule matches, the default for the operation is returned.
    """

    def __init__(
        self,
        rules: tuple[FileAccessRule, ...] = (),
        default_read: AccessLevel = "allow",
        default_write: AccessLevel = "require_approval",
        default_delete: AccessLevel = "require_approval",
    ) -> None:
        self._rules = rules
        self._defaults: dict[str, AccessLevel] = {
            "read": default_read,
            "write": default_write,
            "delete": default_delete,
        }

    def evaluate(self, path: str, operation: str) -> AccessDecision:
        """Evaluate file access for a path and operation.

        Args:
            path: Absolute or ``~``-prefixed file path.
            operation: ``"read"`` | ``"write"`` | ``"delete"``.

        Returns:
            AccessDecision with level and reason.
        """
        if operation not in self._defaults:
            return AccessDecision(level="deny", reason=f"unknown operation: {operation}")

        resolved = os.path.realpath(os.path.expanduser(path))

        for rule in self._rules:
            if self._rule_matches(resolved, rule.paths):
                level = getattr(rule, operation)
                return AccessDecision(level=level, reason=rule.reason)

        return AccessDecision(
            level=self._defaults[operation],
            reason="default policy",
        )

    # ------------------------------------------------------------------
    # Pattern matching
    # ------------------------------------------------------------------

    def _rule_matches(self, resolved: str, patterns: tuple[str, ...]) -> bool:
        """Check if *resolved* absolute path matches any pattern."""
        for pattern in patterns:
            if self._path_matches(resolved, pattern):
                return True
        return False

    @staticmethod
    def _path_matches(resolved: str, pattern: str) -> bool:
        """Match a resolved absolute path against a single glob pattern.

        Supports:
        - ``~`` expansion (``~/.ssh/**``)
        - ``**`` recursive matching (any number of path segments)
        - ``*`` single-segment matching
        - Exact paths

        Patterns are resolved through ``os.path.realpath`` on their
        non-glob prefix so that symlinks (e.g. ``/tmp`` → ``/private/tmp``
        on macOS) are handled correctly.
        """
        expanded = os.path.expanduser(pattern)

        # --- ** recursive glob ---
        if "**" in expanded:
            parts = expanded.split("**", 1)
            prefix = parts[0]
            suffix = parts[1]

            # Resolve symlinks in the prefix (the concrete directory part)
            if prefix:
                prefix = os.path.realpath(prefix.rstrip("/")) + "/"

            if prefix and not resolved.startswith(prefix):
                return False

            if suffix:
                remaining = resolved[len(prefix):] if prefix else resolved
                segments = remaining.split("/")
                for i in range(len(segments)):
                    tail = "/" + "/".join(segments[i:])
                    if fnmatch.fnmatch(tail, suffix):
                        return True
                if fnmatch.fnmatch("/" + segments[-1], suffix):
                    return True
                return False

            # No suffix — prefix/** matches everything under prefix
            return True

        # --- Simple glob or exact path (no **) ---
        # For patterns with *, resolve the directory part and use fnmatch
        if "*" in expanded:
            dir_part, name_part = os.path.split(expanded)
            resolved_dir = os.path.realpath(dir_part)
            resolved_parent, resolved_name = os.path.split(resolved)
            # Only match if the parent directory matches and the filename matches the pattern
            if resolved_parent == resolved_dir:
                return fnmatch.fnmatch(resolved_name, name_part)
            return False

        # Exact path — resolve and compare
        resolved_pattern = os.path.realpath(expanded)
        return resolved == resolved_pattern

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @staticmethod
    def from_dict(data: dict) -> FileAccessPolicy:
        """Create policy from a dict (e.g. parsed YAML ``file_access:`` section)."""
        if not data:
            return FileAccessPolicy()

        rules: list[FileAccessRule] = []
        for rule_data in data.get("rules", []):
            paths = tuple(rule_data.get("paths", []))
            rules.append(
                FileAccessRule(
                    paths=paths,
                    read=rule_data.get("read", "allow"),
                    write=rule_data.get("write", "allow"),
                    delete=rule_data.get("delete", "allow"),
                    reason=rule_data.get("reason", ""),
                )
            )

        return FileAccessPolicy(
            rules=tuple(rules),
            default_read=data.get("default_read", "allow"),
            default_write=data.get("default_write", "require_approval"),
            default_delete=data.get("default_delete", "require_approval"),
        )
