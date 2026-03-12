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
from .policy import NetworkPolicy, SandboxPolicy
from .protocol import Sandbox
from .types import BashResult, ExecResult, SessionInfo, SessionStatus

__all__ = [
    "BashResult",
    "ExecResult",
    "NetworkPolicy",
    "Sandbox",
    "SandboxBackendUnavailable",
    "SandboxConfig",
    "SandboxFactory",
    "SandboxManager",
    "SandboxPolicy",
    "SessionInfo",
    "SessionStatus",
]
