"""Sandbox policy configuration."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True)
class NetworkPolicy:
    """Network access policy."""

    mode: Literal["none", "allow_all", "restricted"] = "allow_all"
    allowed_hosts: tuple[str, ...] = ()  # only used when mode="restricted"
    blocked_hosts: tuple[str, ...] = ()  # only used when mode="allow_all"


@dataclass(frozen=True)
class SandboxPolicy:
    """Unified sandbox policy for all backends.

    This policy is backend-agnostic and gets translated to backend-specific
    configurations (Docker network modes, bwrap args, Seatbelt profiles, etc.)
    """

    # Filesystem
    read_only_paths: tuple[str, ...] = ()
    writable_paths: tuple[str, ...] = ("/tmp",)
    denied_paths: tuple[str, ...] = ()

    # Network
    network: NetworkPolicy = field(default_factory=NetworkPolicy)

    # Resources
    timeout: int = 120
    max_timeout: int = 600
    memory_limit: str = "1g"
    cpu_count: int = 2

    # Backend override
    backend: Literal["auto", "seatbelt", "bubblewrap", "docker"] = "auto"

    @staticmethod
    def from_dict(data: dict) -> SandboxPolicy:
        """Create policy from a dict (e.g. parsed YAML section)."""
        if not data:
            return SandboxPolicy()
        known_fields = {f.name for f in dataclasses.fields(SandboxPolicy)}
        filtered = {k: v for k, v in data.items() if k in known_fields}

        # Handle network field specially
        if "network" in filtered and isinstance(filtered["network"], dict):
            filtered["network"] = NetworkPolicy(**filtered["network"])

        # Convert lists to tuples for immutability
        for field_name in ("read_only_paths", "writable_paths", "denied_paths"):
            if field_name in filtered and isinstance(filtered[field_name], list):
                filtered[field_name] = tuple(filtered[field_name])

        return SandboxPolicy(**filtered)
