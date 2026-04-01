"""Sandbox abstraction for runtime code execution.

Supports multiple backends:
- Docker (stateful container with persistent sessions)
- Seatbelt (macOS sandbox-exec, stateless)
- Bubblewrap (Linux bwrap, stateless)

Use SandboxFactory.create(policy) to get the best available backend.
"""

from .config import SandboxConfig
from .factory import SandboxBackendUnavailable, SandboxFactory
from .manager import SandboxManager
from .policy import DENIED_MOUNTS_HARDCODED, MountSpec, NetworkPolicy, SandboxPolicy
from .protocol import Sandbox
from .types import BashResult, ExecResult, SandboxCapabilities, SessionInfo, SessionStatus

__all__ = [
    "BashResult",
    "DENIED_MOUNTS_HARDCODED",
    "ExecResult",
    "MountSpec",
    "NetworkPolicy",
    "Sandbox",
    "SandboxBackendUnavailable",
    "SandboxCapabilities",
    "SandboxConfig",
    "SandboxFactory",
    "SandboxManager",
    "SandboxPolicy",
    "SessionInfo",
    "SessionStatus",
]
