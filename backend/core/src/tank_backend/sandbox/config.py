"""Sandbox configuration."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass


@dataclass(frozen=True)
class SandboxConfig:
    """Configuration for the Docker sandbox."""

    enabled: bool = True
    image: str = "tank-sandbox:latest"
    workspace_host_path: str = "./workspace"
    memory_limit: str = "1g"
    cpu_count: int = 2
    default_timeout: int = 120
    max_timeout: int = 600
    network_enabled: bool = True

    @staticmethod
    def from_dict(data: dict) -> SandboxConfig:
        """Create config from a dict (e.g. parsed YAML section)."""
        if not data:
            return SandboxConfig(enabled=False)
        known_fields = {f.name for f in dataclasses.fields(SandboxConfig)}
        return SandboxConfig(**{k: v for k, v in data.items() if k in known_fields})
