"""Hook system — user-defined shell scripts on tool lifecycle events."""

from .manager import HookDecision, HookManager, HookSpec

__all__ = ["HookDecision", "HookManager", "HookSpec"]
