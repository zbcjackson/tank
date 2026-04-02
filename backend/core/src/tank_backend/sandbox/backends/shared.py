"""Shared types for native (non-Docker) sandbox backends.

Both Seatbelt and Bubblewrap accept the same policy shape and network
mode enum.  This module avoids duplicating those definitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class NetworkMode(str, Enum):
    """Network access level for the sandbox."""

    NONE = "none"
    ALLOW_ALL = "allow_all"
    RESTRICTED = "restricted"


@dataclass(frozen=True)
class BackendPolicy:
    """Policy consumed by native sandbox backends (Seatbelt, Bubblewrap).

    Created by ``SandboxFactory._to_backend_policy()`` from the unified
    ``SandboxPolicy``.  Backends never parse config directly.
    """

    read_only_paths: tuple[str, ...] = ()
    writable_paths: tuple[str, ...] = ()
    denied_paths: tuple[str, ...] = ()
    network: NetworkMode = NetworkMode.NONE
    allowed_hosts: tuple[str, ...] = ()
    default_timeout: int = 120
    max_timeout: int = 600
    working_dir: str = "/tmp"
