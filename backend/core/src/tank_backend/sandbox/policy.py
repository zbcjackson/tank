"""Sandbox policy configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal

# Paths that are NEVER mountable — reading these files IS the security breach.
# Not overridable by user config.
DENIED_MOUNTS_HARDCODED: tuple[str, ...] = (
    "~/.ssh",
    "~/.gnupg",
    "~/Library/Keychains",
    "/var/run/docker.sock",
)


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
        """Create policy from a dict (e.g. parsed YAML section).

        Supports two config formats:

        **New format** (design doc):
            mounts: [{host: "~", mode: ro}]
            denied_mounts: ["~/.aws"]

        **Legacy format** (current config.yaml):
            workspace_host_path: ./workspace
            network_enabled: true
        """
        if not data:
            return SandboxPolicy(enabled=False)

        # Detect legacy format by presence of legacy-only keys
        if "image" in data or "workspace_host_path" in data or "network_enabled" in data:
            return SandboxPolicy._from_legacy_dict(data)

        return SandboxPolicy._from_new_dict(data)

    @staticmethod
    def _from_legacy_dict(data: dict) -> SandboxPolicy:
        """Parse the old Docker-specific config format."""
        network_enabled = data.get("network_enabled", True)
        network = NetworkPolicy(mode="allow_all" if network_enabled else "none")

        # Legacy format has no mounts — just a workspace path
        return SandboxPolicy(
            enabled=data.get("enabled", True),
            backend="docker",
            docker_image=data.get("image", "tank-sandbox:latest"),
            docker_workspace=data.get("workspace_host_path", "./workspace"),
            memory_limit=data.get("memory_limit", "1g"),
            cpu_count=data.get("cpu_count", 2),
            timeout=data.get("default_timeout", 120),
            max_timeout=data.get("max_timeout", 600),
            network=network,
        )

    @staticmethod
    def _from_new_dict(data: dict) -> SandboxPolicy:
        """Parse the new unified config format."""
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
        elif data.get("network_enabled") is not None:
            mode = "allow_all" if data["network_enabled"] else "none"
            network = NetworkPolicy(mode=mode)

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
            timeout=data.get("timeout", data.get("default_timeout", 120)),
            max_timeout=data.get("max_timeout", 600),
            docker_image=docker_raw.get("image", "tank-sandbox:latest"),
            docker_workspace=docker_raw.get(
                "workspace_host_path", "./workspace"
            ),
        )
