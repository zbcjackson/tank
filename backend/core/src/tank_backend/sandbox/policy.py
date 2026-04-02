"""Sandbox policy configuration."""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field
from typing import Literal


def _build_denied_mounts_hardcoded() -> tuple[str, ...]:
    """Build platform-aware hardcoded denied paths.

    These paths are NEVER mountable — reading them IS the security breach.
    Not overridable by user config.
    """
    common = (
        "~/.ssh",
        "~/.gnupg",
    )
    system = platform.system()
    if system == "Darwin":
        return (*common, "~/Library/Keychains", "/var/run/docker.sock")
    if system == "Linux":
        return (*common, "/var/run/docker.sock")
    # Windows or unknown — just the common ones
    return common


DENIED_MOUNTS_HARDCODED: tuple[str, ...] = _build_denied_mounts_hardcoded()


@dataclass(frozen=True)
class MountSpec:
    """A single mount specification: host path + access mode."""

    host: str
    mode: Literal["ro", "rw"] = "ro"


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

    The ``mounts`` field is the primary way to declare filesystem access.
    ``read_only_paths`` and ``writable_paths`` are computed from ``mounts``
    at construction time (via ``from_dict``).  ``denied_paths`` merges
    ``denied_mounts_hardcoded`` (always present) with user-configurable
    ``denied_mounts``.
    """

    # Filesystem — computed from mounts + denied_mounts
    read_only_paths: tuple[str, ...] = ()
    writable_paths: tuple[str, ...] = ("/tmp",)
    denied_paths: tuple[str, ...] = ()

    # High-level mount config (preserved for Docker same-path translation)
    mounts: tuple[MountSpec, ...] = ()
    denied_mounts: tuple[str, ...] = ()

    # Network
    network: NetworkPolicy = field(default_factory=NetworkPolicy)

    # Resources
    timeout: int = 120
    max_timeout: int = 600
    memory_limit: str = "1g"
    cpu_count: int = 2

    # Backend override
    backend: Literal["auto", "seatbelt", "bubblewrap", "docker"] = "auto"

    # Feature toggle
    enabled: bool = True

    # Docker-specific settings
    docker_image: str = "tank-sandbox:latest"
    docker_workspace: str = "./workspace"

    @staticmethod
    def from_dict(data: dict) -> SandboxPolicy:
        """Create policy from a dict (e.g. parsed YAML ``sandbox:`` section)."""
        if not data:
            return SandboxPolicy(enabled=False)

        # Parse mounts
        mounts_raw = data.get("mounts", [])
        mounts = tuple(
            MountSpec(host=m["host"], mode=m.get("mode", "ro"))
            for m in mounts_raw
            if isinstance(m, dict) and "host" in m
        )

        # Expand mounts to read_only_paths / writable_paths
        ro_paths: list[str] = []
        rw_paths: list[str] = ["/tmp"]
        for m in mounts:
            expanded = os.path.expanduser(m.host)
            if m.mode == "rw":
                rw_paths.append(expanded)
            else:
                ro_paths.append(expanded)

        # Merge denied_mounts_hardcoded + user denied_mounts
        user_denied = data.get("denied_mounts", [])
        all_denied = [
            os.path.expanduser(p)
            for p in (*DENIED_MOUNTS_HARDCODED, *user_denied)
        ]

        # Parse network
        network = NetworkPolicy()
        net_raw = data.get("network")
        if isinstance(net_raw, dict):
            network = NetworkPolicy(**{
                k: (tuple(v) if isinstance(v, list) else v)
                for k, v in net_raw.items()
            })

        # Docker-specific
        docker_raw = data.get("docker", {})

        return SandboxPolicy(
            enabled=data.get("enabled", True),
            backend=data.get("backend", "auto"),
            mounts=mounts,
            denied_mounts=tuple(data.get("denied_mounts", [])),
            read_only_paths=tuple(ro_paths),
            writable_paths=tuple(rw_paths),
            denied_paths=tuple(all_denied),
            network=network,
            memory_limit=data.get("memory_limit", "1g"),
            cpu_count=data.get("cpu_count", 2),
            timeout=data.get("timeout", 120),
            max_timeout=data.get("max_timeout", 600),
            docker_image=docker_raw.get("image", "tank-sandbox:latest"),
            docker_workspace=docker_raw.get(
                "workspace_host_path", "./workspace"
            ),
        )
