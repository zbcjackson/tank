"""Sandbox configuration."""

from __future__ import annotations

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
        return SandboxConfig(
            enabled=data.get("enabled", True),
            image=data.get("image", "tank-sandbox:latest"),
            workspace_host_path=data.get("workspace_host_path", "./workspace"),
            memory_limit=data.get("memory_limit", "1g"),
            cpu_count=data.get("cpu_count", 2),
            default_timeout=data.get("default_timeout", 120),
            max_timeout=data.get("max_timeout", 600),
            network_enabled=data.get("network_enabled", True),
        )
