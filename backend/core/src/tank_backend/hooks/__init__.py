"""Hook system — user-defined shell scripts on tool lifecycle events."""

from .allowlist import HookAllowlist, HookIdentity
from .manager import HookDecision, HookManager, HookSpec

__all__ = ["HookAllowlist", "HookDecision", "HookIdentity", "HookManager", "HookSpec"]
